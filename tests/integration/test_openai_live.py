"""Live OpenAI integration tests.

Run with::

    OPENAI_API_KEY=sk-... AEGIS_MODEL=gpt-4o-mini RUN_LIVE_TESTS=1 \\
        pytest tests/integration/test_openai_live.py -v

To re-record cassettes for offline replay, delete the relevant file in
``cassettes/`` first.
"""

from __future__ import annotations

import os

import pytest

from aegis import Aegis
from aegis.providers import OpenAI
from aegis.providers.base import Message

MODEL = os.environ.get("AEGIS_MODEL", "gpt-4o-mini")


@pytest.fixture(scope="module")
def provider() -> OpenAI:
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    return OpenAI(model=MODEL)


@pytest.mark.live
@pytest.mark.asyncio
async def test_basic_completion(provider: OpenAI):
    """Single-turn completion — sanity check the adapter."""
    r = await provider.complete(
        [Message.user("Reply with the single word: pong")],
        temperature=0.0,
        max_tokens=10,
    )
    assert "pong" in r.text.lower()
    assert r.tokens_in > 0
    assert r.tokens_out > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_json_mode(provider: OpenAI):
    r = await provider.complete(
        [
            Message.system("Respond with JSON only."),
            Message.user('Reply with: {"answer": 42}'),
        ],
        json_only=True,
        max_tokens=50,
    )
    import json

    parsed = json.loads(r.text)
    assert parsed["answer"] == 42


@pytest.mark.live
@pytest.mark.asyncio
async def test_multi_turn_tool_call(provider: OpenAI):
    """The bug that broke real-LLM use in v0.0 — must work now."""
    from aegis.providers.base import Tool

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
    # Turn 1: ask for the tool
    r1 = await provider.complete(
        [Message.user("What's the weather in NYC? Use the get_weather tool.")],
        tools=tools,
        max_tokens=200,
    )
    assert r1.tool_calls, "Expected the model to call the tool"

    # Turn 2: feed back the tool result, expect a natural-language answer
    msgs = [
        Message.user("What's the weather in NYC? Use the get_weather tool."),
        Message.assistant(content=r1.text, tool_calls=r1.tool_calls),
        Message.tool_result(
            tool_call_id=r1.tool_calls[0].id,
            name=r1.tool_calls[0].name,
            content='{"temp_f": 72, "condition": "sunny"}',
        ),
    ]
    r2 = await provider.complete(msgs, tools=tools, max_tokens=80)
    assert r2.text
    assert "72" in r2.text or "sunny" in r2.text.lower()


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_pipeline_arithmetic(tmp_path):
    """End-to-end: simple math task should complete and verify successfully."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    aegis = Aegis(
        provider=OpenAI(model=MODEL),
        cache_dir=tmp_path,
        enable_cache=False,
    )
    result = await aegis.run("What is 7 times 8? Reply with just the integer.")
    assert result.audit.succeeded
    # The value shape depends on the synthesized schema; flatten and search.
    flat = str(result.value)
    assert "56" in flat


@pytest.mark.live
@pytest.mark.asyncio
async def test_full_pipeline_with_risk_profile(tmp_path):
    """End-to-end: research-style goal should trigger citation-hallucination defenses."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    aegis = Aegis(
        provider=OpenAI(model=MODEL),
        cache_dir=tmp_path,
        enable_cache=False,
    )
    result = await aegis.run(
        "Name 3 well-known Python web frameworks and provide a one-line description for each."
    )
    risk_ids = {r.id for r in result.audit.risks.risks}
    # FMEA + keyword merger should always surface at least one of these:
    assert risk_ids & {
        "citation-hallucination",
        "entity-fabrication",
        "truncated-list",
        "schema-drift",
    }, f"Expected research-style risks; got {risk_ids}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_streaming(provider: OpenAI):
    chunks = []
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
    assert completion is not None
    assert "hello" in completion.text.lower()
    assert chunks  # we saw at least one delta
