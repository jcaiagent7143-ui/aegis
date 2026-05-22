"""End-to-end MCP integration tests.

Spawns the real `aegis mcp` subprocess and drives it via the official MCP
client SDK. This is the test that would have caught two bugs surfaced by
external testing of v0.5.0:

  1. Env-var-not-propagated-to-subprocess (the #1 MCP-integration footgun)
  2. `aegis_run` silently fell back to Mock without telling the caller why

These tests use the bundled Mock provider so they run in CI without any
API keys — but they pass `env` explicitly to the MCP subprocess to verify
the propagation path *would* work with a real key.

Each test uses its own ``tmp_path``-scoped cache directory so previous test
runs don't contaminate via the harness cache.

Run with::

    pytest tests/integration/test_mcp_e2e.py -v
"""

from __future__ import annotations

import json
import os
from shutil import which

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

pytestmark = pytest.mark.skipif(
    which("aegis") is None,
    reason="`aegis` not on PATH — install the package first",
)


def _server_params(
    cache_dir: str, env_override: dict[str, str] | None = None
) -> StdioServerParameters:
    """Build StdioServerParameters with a per-test cache directory.

    Critical: MCP subprocesses do NOT inherit the parent shell env. Every
    var the subprocess needs must be in `env` here — same gotcha real users
    hit when configuring `aegis mcp` in their AI tool's MCP config.
    """
    env = {"AEGIS_CACHE_DIR": cache_dir}
    for k in ("PATH", "HOME", "LANG", "LC_ALL"):
        if k in os.environ:
            env[k] = os.environ[k]
    if env_override:
        env.update(env_override)
    return StdioServerParameters(command="aegis", args=["mcp"], env=env)


def _first_text(result) -> str:
    for c in result.content:
        if hasattr(c, "text"):
            return c.text
    return ""


@pytest.mark.asyncio
async def test_initialize_advertises_four_tools(tmp_path):
    """Server starts and advertises exactly the 4 documented tools."""
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        assert init.serverInfo.name == "aegis"

        tools = await session.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert tool_names == {
            "aegis_run",
            "aegis_assess",
            "aegis_inspect",
            "aegis_list_risks",
        }, f"unexpected tools: {tool_names}"

        for t in tools.tools:
            assert t.description and len(t.description) > 30, (
                f"{t.name} has poor description: {t.description!r}"
            )
            assert isinstance(t.inputSchema, dict)
            assert t.inputSchema.get("type") == "object"


@pytest.mark.asyncio
async def test_list_risks_returns_full_catalog(tmp_path):
    """Static catalog tool — no LLM call needed."""
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("aegis_list_risks", {})
        data = json.loads(_first_text(result))
        assert data["count"] >= 30
        ids = {e["id"] for e in data["catalog"]}
        assert "citation-hallucination" in ids
        assert "arithmetic-drift" in ids


@pytest.mark.asyncio
async def test_assess_identifies_research_risks(tmp_path):
    """Assess stage runs analyze + assess via Mock provider."""
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "aegis_assess",
            {"goal": "Find the top 5 startups in YC W26 batch"},
        )
        data = json.loads(_first_text(result))
        risk_ids = {r["id"] for r in data["risks"]}
        # Keyword-triggered risks always surface (added by fmea.py merger),
        # regardless of provider quality
        assert risk_ids & {
            "citation-hallucination",
            "entity-fabrication",
            "ranking-ambiguity",
            "truncated-list",
        }


@pytest.mark.asyncio
async def test_run_full_pipeline_with_mock_provider(tmp_path):
    """aegis_run executes all 5 stages; audit round-trips via aegis_inspect."""
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        run_result = await session.call_tool("aegis_run", {"goal": "What is 2 + 2?"})
        run_data = json.loads(_first_text(run_result))
        assert run_data["succeeded"] is True
        assert run_data["run_id"].startswith("run_")
        assert "BaseModel" in run_data["harness_code"]
        assert run_data["cached"] is False, "fresh tmp_path should never hit cache"

        # Round-trip via aegis_inspect — proves the audit was persisted
        inspect_result = await session.call_tool("aegis_inspect", {"run_id": run_data["run_id"]})
        inspect_data = json.loads(_first_text(inspect_result))
        stages = {s["name"] for s in inspect_data["stages"]}
        assert {"analyze", "assess", "synthesize", "execute", "verify"} <= stages


@pytest.mark.asyncio
async def test_mock_fallback_detectable_by_caller(tmp_path):
    """When no provider key is set, Mock fires — caller must be able to detect.

    Regression for the #1 MCP-integration bug: developers configure `aegis
    mcp` without setting OPENAI_API_KEY in the env block. Aegis silently
    uses Mock and placeholder output confuses everyone. With Mock the
    trivial verifier passes so succeeded=True; the diagnostic only surfaces
    when succeeded=False. So we assert that response shape includes
    provider="mock" so clients can detect the situation themselves.
    """
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("aegis_run", {"goal": "Pick a random number"})
        data = json.loads(_first_text(result))
        assert data["provider"] == "mock"
        value = data.get("value")
        if isinstance(value, dict):
            serialized = json.dumps(value)
            assert "[mock]" in serialized or value.get("value", "").startswith("[mock]")


@pytest.mark.asyncio
async def test_unknown_tool_returns_structured_error(tmp_path):
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("aegis_definitely_not_a_tool", {})
        text = _first_text(result)
        data = json.loads(text)
        assert "error" in data
        assert "aegis_definitely_not_a_tool" in data["error"]


@pytest.mark.asyncio
async def test_missing_required_arg_rejected(tmp_path):
    """MCP SDK's input-schema validation catches this before our handler runs."""
    async with (
        stdio_client(_server_params(str(tmp_path))) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("aegis_assess", {})
        text = _first_text(result).lower()
        assert "goal" in text or "required" in text or "error" in text
