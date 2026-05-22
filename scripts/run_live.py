"""Full live-validation script — run this to prove Aegis works end-to-end.

Usage::

    export OPENAI_API_KEY=sk-...
    export AEGIS_MODEL=gpt-5.4-nano-2026-03-17  # or gpt-4o-mini
    python scripts/run_live.py

What it does, in order:

  1. Adapter health check — single-turn completion.
  2. Multi-turn tool-use check — the v0.0 bug regression.
  3. JSON-mode check.
  4. Streaming check.
  5. Full 5-stage pipeline on three diverse goals.
  6. Verifier limits test (timeout enforcement).
  7. Mini benchmark — 3 tasks × {raw, fixed, aegis} → tabular results.

Exits 0 if everything green, 1 otherwise. Prints a final summary table.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

from aegis import Aegis
from aegis.providers import OpenAI
from aegis.providers.base import Message, Tool


def banner(text: str) -> None:
    print(f"\n{'═' * 72}\n  {text}\n{'═' * 72}")


def check(name: str, ok: bool, detail: str = "") -> None:
    icon = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {icon} {name}" + (f"  ({detail})" if detail else ""))


async def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("AEGIS_MODEL", "gpt-4o-mini")
    if not api_key:
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr)
        return 2

    print(f"Model: {model}")
    provider = OpenAI(model=model)
    failures: list[str] = []

    # ─── 1. Adapter health ──────────────────────────────────────────────
    banner("1 · ADAPTER HEALTH")
    try:
        r = await provider.complete(
            [Message.user("Reply with the single word: pong")],
            temperature=0.0,
            max_tokens=10,
        )
        ok = "pong" in r.text.lower()
        check("single-turn completion", ok, f"got: {r.text[:40]!r}")
        if not ok:
            failures.append("single-turn")
    except Exception as e:
        check("single-turn completion", False, f"{type(e).__name__}: {e}")
        failures.append("single-turn")

    # ─── 2. Multi-turn tool use ─────────────────────────────────────────
    banner("2 · MULTI-TURN TOOL USE (v0.0 regression)")
    try:
        tools = [
            Tool(
                name="get_weather",
                description="Get current temperature in a city",
                parameters_schema={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            )
        ]
        msg = "What's the weather in NYC? Use the get_weather tool."
        r1 = await provider.complete([Message.user(msg)], tools=tools, max_tokens=200)
        check(
            "turn 1 emits tool_call",
            bool(r1.tool_calls),
            f"{len(r1.tool_calls)} call(s)",
        )

        msgs = [
            Message.user(msg),
            Message.assistant(content=r1.text, tool_calls=r1.tool_calls),
            Message.tool_result(
                tool_call_id=r1.tool_calls[0].id,
                name=r1.tool_calls[0].name,
                content='{"temp_f": 72, "condition": "sunny"}',
            ),
        ]
        r2 = await provider.complete(msgs, tools=tools, max_tokens=80)
        ok = bool(r2.text) and ("72" in r2.text or "sunny" in r2.text.lower())
        check("turn 2 with tool_result returns NL answer", ok, r2.text[:80])
        if not ok:
            failures.append("multi-turn-tool")
    except Exception as e:
        check("multi-turn tool flow", False, f"{type(e).__name__}: {e}")
        failures.append("multi-turn-tool")

    # ─── 3. JSON mode ───────────────────────────────────────────────────
    banner("3 · JSON MODE")
    try:
        r = await provider.complete(
            [Message.system("Respond with JSON only."), Message.user('Reply with {"x":42}')],
            json_only=True,
            max_tokens=30,
        )
        parsed = json.loads(r.text)
        ok = parsed.get("x") == 42
        check("json_only=True returns valid parseable JSON", ok, f"got: {r.text}")
        if not ok:
            failures.append("json-mode")
    except Exception as e:
        check("json mode", False, f"{type(e).__name__}: {e}")
        failures.append("json-mode")

    # ─── 4. Streaming ───────────────────────────────────────────────────
    banner("4 · STREAMING")
    try:
        chunks: list[str] = []
        completion = None
        async for kind, payload in provider.stream(
            [Message.user("Reply with: hello world")],
            temperature=0.0,
            max_tokens=20,
        ):
            if kind == "delta":
                chunks.append(payload)
            elif kind == "done":
                completion = payload
        ok = bool(chunks) and completion is not None and "hello" in completion.text.lower()
        check(
            "stream emits deltas and final completion",
            ok,
            f"{len(chunks)} chunks, text={completion.text[:40] if completion else 'None'!r}",
        )
        if not ok:
            failures.append("streaming")
    except Exception as e:
        check("streaming", False, f"{type(e).__name__}: {e}")
        failures.append("streaming")

    # ─── 5. Full pipeline ───────────────────────────────────────────────
    banner("5 · FULL AEGIS PIPELINE  (3 diverse goals)")
    aegis = Aegis(provider=provider, cache_dir="/tmp/aegis-live", enable_cache=False)
    goals = [
        ("arithmetic", "What is 7 times 8? Reply with just the integer."),
        ("research", "Name 3 well-known Python web frameworks with one-line descriptions."),
        ("structured", "List exactly 5 noble gases as JSON."),
    ]
    for label, g in goals:
        try:
            t0 = time.perf_counter()
            r = await aegis.run(g)
            dt = (time.perf_counter() - t0) * 1000
            risks = [risk.id for risk in r.audit.risks.risks]
            check(
                f"[{label}] pipeline run",
                r.audit.succeeded,
                f"risks={risks}, repairs={r.audit.repairs}, tokens={r.audit.total_tokens}, dt={dt:.0f}ms",
            )
            if not r.audit.succeeded:
                failures.append(f"pipeline-{label}")
        except Exception as e:
            check(f"[{label}] pipeline run", False, f"{type(e).__name__}: {e}")
            failures.append(f"pipeline-{label}")

    # ─── 6. Sandbox limits ──────────────────────────────────────────────
    banner("6 · SANDBOX TIMEOUT ENFORCEMENT")
    try:
        from aegis.synthesize.sandbox import SandboxTimeout, run_with_limits

        def loop_forever() -> None:
            i = 0
            while True:
                i += 1

        try:
            run_with_limits(loop_forever, timeout_s=0.2, memory_mb=None)
            check("infinite loop killed by timeout", False, "did NOT raise")
            failures.append("sandbox-timeout")
        except SandboxTimeout:
            check("infinite loop killed by timeout", True, "raised SandboxTimeout as expected")
    except Exception as e:
        check("sandbox timeout", False, f"{type(e).__name__}: {e}")
        failures.append("sandbox-timeout")

    # ─── 7. Mini-benchmark ──────────────────────────────────────────────
    banner("7 · MINI-BENCHMARK  (raw vs fixed vs aegis)")
    try:
        from benchmarks.run import run as bench_run

        results = await bench_run(quick=True)
        print("\n  Mode   | pass/total | avg tokens | avg latency")
        print("  -------|-----------|-----------|-------------")
        for mode in results["modes"]:
            s = results["summary"][mode]
            print(
                f"  {mode:>5}  |  {s['passed']:>3}/{s['total']:>3}    |"
                f"  {s['avg_tokens']:>8.0f}  |  {s['avg_latency_ms']:>6.0f}ms"
            )
    except Exception as e:
        check("benchmark", False, f"{type(e).__name__}: {e}")
        failures.append("benchmark")

    # ─── final ──────────────────────────────────────────────────────────
    banner("SUMMARY")
    if failures:
        print(f"  \033[31m✗ {len(failures)} failure(s):\033[0m {failures}")
        return 1
    print("  \033[32m✓ all live checks green\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
