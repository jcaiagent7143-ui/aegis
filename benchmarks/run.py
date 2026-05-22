"""Benchmark runner — compare raw / fixed / aegis modes across tasks.

Usage::

    python -m benchmarks.run                # full sweep
    python -m benchmarks.run --quick        # smoke (5 tasks)
    python -m benchmarks.run --modes aegis  # only the dynamic-harness mode
    python -m benchmarks.run --out results/foo.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from aegis import Aegis
from aegis.providers import auto_provider
from aegis.providers.base import Message
from benchmarks.tasks import Task, discover

Mode = Literal["raw", "fixed", "aegis"]


class GenericOutput(BaseModel):
    value: Any
    rationale: str = ""


async def run_raw(task: Task) -> dict[str, Any]:
    provider = auto_provider()
    t0 = time.perf_counter()
    resp = await provider.complete([Message.user(task.goal)], temperature=0.0)
    dt = (time.perf_counter() - t0) * 1000
    try:
        parsed = json.loads(resp.text)
    except json.JSONDecodeError:
        parsed = resp.text.strip()
    return {
        "value": parsed,
        "passed": task.check(parsed),
        "tokens": resp.tokens_in + resp.tokens_out,
        "latency_ms": dt,
        "tool_calls": 0,
        "repairs": 0,
    }


async def run_fixed(task: Task) -> dict[str, Any]:
    """Generic harness: ask for JSON {value, rationale}, validate with pydantic."""
    provider = auto_provider()
    t0 = time.perf_counter()
    schema = GenericOutput.model_json_schema()
    prompt = (
        f"{task.goal}\n\n"
        f"Respond with raw JSON only matching this schema:\n{json.dumps(schema, indent=2)}"
    )
    resp = await provider.complete([Message.user(prompt)], temperature=0.0, json_only=True)
    dt = (time.perf_counter() - t0) * 1000
    try:
        out = GenericOutput.model_validate_json(resp.text)
        passed = task.check(out.model_dump())
        value: Any = out.value
    except Exception:
        passed = False
        value = resp.text
    return {
        "value": value,
        "passed": passed,
        "tokens": resp.tokens_in + resp.tokens_out,
        "latency_ms": dt,
        "tool_calls": 0,
        "repairs": 0,
    }


async def run_aegis(task: Task) -> dict[str, Any]:
    aegis = Aegis()
    t0 = time.perf_counter()
    result = await aegis.run(task.goal)
    dt = (time.perf_counter() - t0) * 1000
    return {
        "value": result.value,
        "passed": task.check(result.value),
        "tokens": result.audit.total_tokens,
        "latency_ms": dt,
        "tool_calls": len(result.audit.tool_calls),
        "repairs": result.audit.repairs,
    }


RUNNERS = {"raw": run_raw, "fixed": run_fixed, "aegis": run_aegis}


async def run(
    *,
    quick: bool = False,
    modes: list[Mode] | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    tasks = discover()
    if quick:
        tasks = tasks[:5]
    modes = list(modes or ["raw", "fixed", "aegis"])

    print(f"Tasks: {len(tasks)}    Modes: {modes}")
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for task in tasks:
        results[task.name] = {}
        for mode in modes:
            print(f"  [{mode:>5}] {task.name} …", end=" ", flush=True)
            try:
                row = await RUNNERS[mode](task)
            except Exception as e:
                row = {
                    "value": None,
                    "passed": False,
                    "tokens": 0,
                    "latency_ms": 0,
                    "tool_calls": 0,
                    "repairs": 0,
                    "error": f"{type(e).__name__}: {e}",
                }
            results[task.name][mode] = row
            print("✓" if row["passed"] else "✗")

    summary = _summarize(results, modes)
    output = {"tasks": results, "summary": summary, "modes": modes}

    out = out or Path("benchmarks/results") / f"{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nWrote {out}")
    print("\nSummary:")
    for mode in modes:
        s = summary[mode]
        print(
            f"  {mode:>5}: pass={s['passed']}/{s['total']} "
            f"({100 * s['pass_rate']:.0f}%)   "
            f"avg_tokens={s['avg_tokens']:.0f}   "
            f"avg_latency={s['avg_latency_ms']:.0f}ms"
        )
    return output


def _summarize(results, modes: list[Mode]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for mode in modes:
        rows = [results[t][mode] for t in results]
        total = len(rows)
        passed = sum(1 for r in rows if r["passed"])
        summary[mode] = {
            "total": total,
            "passed": passed,
            "pass_rate": passed / total if total else 0,
            "avg_tokens": sum(r["tokens"] for r in rows) / total if total else 0,
            "avg_latency_ms": sum(r["latency_ms"] for r in rows) / total if total else 0,
            "avg_tool_calls": sum(r["tool_calls"] for r in rows) / total if total else 0,
            "avg_repairs": sum(r["repairs"] for r in rows) / total if total else 0,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis benchmark runner")
    parser.add_argument("--quick", action="store_true", help="Run only 5 tasks")
    parser.add_argument("--modes", nargs="+", choices=list(RUNNERS), default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(run(quick=args.quick, modes=args.modes, out=args.out))


if __name__ == "__main__":
    main()
