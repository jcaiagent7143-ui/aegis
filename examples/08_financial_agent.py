"""Example 08 — Financial buy/sell agent with self-generated guardrails.

This is the "real money" stress test for Aegis. We register a set of mock
market-data tools (so it runs offline) and ask three increasingly tricky
goals, comparing:

  * RAW provider call  — just ask the LLM, take whatever it says.
  * AEGIS pipeline     — same goal, full 5-stage pipeline with synthesized
                         harness, verifier, repair loop.

For each run we print:
  * the recommendation,
  * the synthesized harness (so you can see what defenses Aegis built),
  * whether the verifier passed,
  * what failure modes Aegis identified up front.

Usage::

    export OPENAI_API_KEY=sk-...
    export AEGIS_MODEL=gpt-5.4-nano-2026-03-17   # or gpt-4o-mini
    python examples/08_financial_agent.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from aegis import Aegis
from aegis.execute.tool_registry import default_registry, tool
from aegis.providers import OpenAI
from aegis.providers.base import Message

MODEL = os.environ.get("AEGIS_MODEL", "gpt-4o-mini")

# ─────────────────────────────────────────────────────────────────────────
# Mock market-data layer — pretend this is a Polygon/Alpaca/IEX client.
# Everything is deterministic and offline; swap for real APIs in production.
# ─────────────────────────────────────────────────────────────────────────

_MARKET: dict[str, dict[str, Any]] = {
    "NVDA": {
        "name": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "price": 142.80,
        "pe": 51.2,
        "eps_ttm": 2.79,
        "moving_avg_200d": 118.30,
        "market_cap_b": 3520.0,
    },
    "AAPL": {
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "price": 198.45,
        "pe": 31.7,
        "eps_ttm": 6.26,
        "moving_avg_200d": 188.20,
        "market_cap_b": 3040.0,
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "exchange": "NASDAQ",
        "price": 421.10,
        "pe": 35.8,
        "eps_ttm": 11.76,
        "moving_avg_200d": 405.60,
        "market_cap_b": 3130.0,
    },
}

_NEWS: dict[str, list[dict[str, str]]] = {
    "NVDA": [
        {
            "date": "2026-05-19",
            "headline": "NVIDIA Q1 beats: data-center revenue up 71% YoY",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001045810&type=10-Q",
        },
        {
            "date": "2026-05-15",
            "headline": "AMD MI400 launch could erode NVIDIA's accelerator margin",
            "url": "https://example.com/news/amd-mi400",
        },
    ],
    "AAPL": [
        {
            "date": "2026-05-02",
            "headline": "Apple Q2 FY26: iPhone revenue flat, services hit record",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-Q",
        },
    ],
    "MSFT": [
        {
            "date": "2026-04-25",
            "headline": "Microsoft Azure growth re-accelerates to 31%",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000789019&type=10-Q",
        },
    ],
}


@tool(
    name="validate_ticker",
    description="Validate a stock ticker. Returns {name, exchange} for real tickers; raises for fakes.",
    parameters={
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    },
)
def validate_ticker(ticker: str) -> dict[str, str]:
    info = _MARKET.get(ticker.upper())
    if info is None:
        raise ValueError(f"Unknown ticker: {ticker}. Not listed on any supported exchange.")
    return {"name": info["name"], "exchange": info["exchange"]}


@tool(
    name="get_quote",
    description=(
        "Get a live quote for a ticker. Returns {price, pe, eps_ttm, "
        "moving_avg_200d, market_cap_b}."
    ),
    parameters={
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    },
)
def get_quote(ticker: str) -> dict[str, Any]:
    info = _MARKET.get(ticker.upper())
    if info is None:
        raise ValueError(f"Unknown ticker: {ticker}")
    return {k: v for k, v in info.items() if k not in ("name", "exchange")}


@tool(
    name="get_news",
    description="Recent news headlines for a ticker. Returns list of {date, headline, url}.",
    parameters={
        "type": "object",
        "properties": {"ticker": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
        "required": ["ticker"],
    },
)
def get_news(ticker: str, limit: int = 5) -> list[dict[str, str]]:
    return _NEWS.get(ticker.upper(), [])[:limit]


def build_aegis() -> Aegis:
    registry = default_registry()
    for fn in (validate_ticker, get_quote, get_news):
        registry.register(fn)
    return Aegis(
        provider=OpenAI(model=MODEL),
        tools=registry,
        cache_dir="/tmp/aegis-financial",
        enable_cache=False,
    )


# ─────────────────────────────────────────────────────────────────────────
# Three goals designed to stress different failure modes
# ─────────────────────────────────────────────────────────────────────────

GOALS = [
    (
        "real-ticker-buy-rec",
        "Should I buy NVDA at today's price? Look at the current quote, P/E, "
        "the 200-day moving average, and the last few news headlines. Return "
        "a structured recommendation with confidence and at least one caveat.",
    ),
    (
        "fake-ticker-trap",
        "Should I buy BIOGENIX-XR at today's price? It's a hot biotech I heard about. "
        "Look up the quote and any recent news, then give me a recommendation.",
    ),
    (
        "arithmetic-trap",
        "Tell me the P/E of MSFT computed yourself from price and EPS. "
        "Show your work. Return the computed value rounded to 2 decimals.",
    ),
]


# ─────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────


def section(title: str) -> None:
    print(f"\n{'═' * 78}\n  {title}\n{'═' * 78}")


def render(label: str, value: Any, *, max_len: int = 400) -> None:
    s = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
    if len(s) > max_len:
        s = s[:max_len] + "…"
    print(f"\n[{label}]\n{s}")


async def run_raw(goal: str) -> dict[str, Any]:
    """No harness, no tools, no schema — just ask and take whatever comes back."""
    provider = OpenAI(model=MODEL)
    t0 = time.perf_counter()
    r = await provider.complete([Message.user(goal)], temperature=0.0, max_tokens=600)
    return {
        "value": r.text,
        "tokens": r.tokens_in + r.tokens_out,
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }


async def run_aegis(aegis: Aegis, goal: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    result = await aegis.run(goal)
    return {
        "succeeded": result.audit.succeeded,
        "value": result.value,
        "risks": [r.id for r in result.audit.risks.risks],
        "repairs": result.audit.repairs,
        "tokens": result.audit.total_tokens,
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "harness": result.harness_code,
        "tool_calls": [(t["name"], t.get("ok")) for t in result.audit.tool_calls],
        "verify_failures": _last_verify_failures(result),
    }


def _last_verify_failures(result: Any) -> list[str]:
    for stage in reversed(result.audit.stages):
        if stage.name.startswith("verify"):
            return list(stage.output.get("failures", []))
    return []


async def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: set OPENAI_API_KEY")
        return 2

    print(f"Model: {MODEL}")
    aegis = build_aegis()

    for label, goal in GOALS:
        section(f"GOAL [{label}]")
        print(f"  {goal}\n")

        # 1. RAW provider call
        print("─── RAW PROVIDER (no harness) " + "─" * 47)
        raw = await run_raw(goal)
        render("raw answer", raw["value"], max_len=600)
        print(f"\n[raw cost] {raw['tokens']} tokens, {raw['latency_ms']:.0f}ms")

        # 2. AEGIS pipeline
        print("\n─── AEGIS (self-generated harness) " + "─" * 42)
        aeg = await run_aegis(aegis, goal)
        render("identified risks", aeg["risks"])
        render("generated harness", aeg["harness"], max_len=1200)
        render("tool calls", aeg["tool_calls"])
        render("answer", aeg["value"])
        render("verifier failures", aeg["verify_failures"])
        verdict = "✓ SUCCEEDED" if aeg["succeeded"] else "✗ FAILED VERIFICATION"
        print(
            f"\n[aegis] {verdict}  |  {aeg['tokens']} tokens  |  "
            f"{aeg['repairs']} repair(s)  |  {aeg['latency_ms']:.0f}ms"
        )

    section("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
