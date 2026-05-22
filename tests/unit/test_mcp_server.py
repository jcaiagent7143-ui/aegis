"""Tests for the MCP server's tool handlers + tool registration.

We test the handler functions directly (no stdio plumbing) and verify the
server registers exactly the four tools we expect with valid input schemas.
"""

from __future__ import annotations

import json

import pytest

from aegis.mcp import server as mcp_server


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch, tmp_path):
    """Force Mock provider + temp cache for every test in this module."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("AEGIS_CACHE_DIR", str(tmp_path / "cache"))
    # Re-import constants since DEFAULT_CACHE_DIR is set at import time
    monkeypatch.setattr(mcp_server, "DEFAULT_CACHE_DIR", tmp_path / "cache")


class TestServerSetup:
    def test_server_registers_four_tools(self):
        # We can't easily list the tools the @decorator registered without
        # invoking the protocol, so check that all four handlers exist.
        assert callable(mcp_server._handle_run)
        assert callable(mcp_server._handle_assess)
        assert callable(mcp_server._handle_inspect)
        assert callable(mcp_server._handle_list_risks)

    def test_build_server_succeeds(self):
        srv = mcp_server._build_server()
        assert srv is not None

    def test_aegis_run_input_schema_requires_goal(self):
        schema = mcp_server._AEGIS_RUN_INPUT_SCHEMA
        assert schema["type"] == "object"
        assert "goal" in schema["properties"]
        assert "goal" in schema["required"]

    def test_aegis_assess_schema(self):
        schema = mcp_server._AEGIS_ASSESS_INPUT_SCHEMA
        assert schema["required"] == ["goal"]


class TestListRisks:
    @pytest.mark.asyncio
    async def test_returns_full_catalog(self):
        out = await mcp_server._handle_list_risks({})
        data = json.loads(out)
        assert data["count"] >= 30
        ids = {e["id"] for e in data["catalog"]}
        assert "citation-hallucination" in ids
        assert "arithmetic-drift" in ids
        # Every entry has the documented shape
        for e in data["catalog"]:
            assert {
                "id",
                "name",
                "description",
                "typical_level",
                "trigger_keywords",
                "defense_hints",
            } <= set(e.keys())


class TestInspectErrorPath:
    @pytest.mark.asyncio
    async def test_unknown_run_id_returns_error_json(self):
        out = await mcp_server._handle_inspect({"run_id": "does-not-exist"})
        data = json.loads(out)
        assert "error" in data


class TestRunHandler:
    @pytest.mark.asyncio
    async def test_handle_run_returns_audit_summary(self, monkeypatch):
        # Mock provider scripted to walk the full pipeline
        from aegis.providers.mock import Mock

        scripted = [
            json.dumps(
                {
                    "summary": "g",
                    "deliverable": "d",
                    "output_schema_hint": "x",
                    "needed_tools": [],
                    "open_questions": [],
                }
            ),
            json.dumps(
                {"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}
            ),
            "from pydantic import BaseModel\n\nclass Output(BaseModel):\n    value: str = ''\n\n"
            "ALLOWED_TOOLS: list[str] = []\n\ndef verify(output): return []\n",
            json.dumps({"value": "answer"}),
        ]

        from aegis import Aegis

        def _factory():
            return Aegis(
                provider=Mock(responses=scripted),
                cache_dir=mcp_server.DEFAULT_CACHE_DIR,
                enable_cache=False,
            )

        monkeypatch.setattr(mcp_server, "_make_aegis", _factory)

        out = await mcp_server._handle_run({"goal": "hello"})
        data = json.loads(out)
        assert data["succeeded"] is True
        assert data["value"] == {"value": "answer"}
        assert "run_id" in data
        assert "harness_code" in data
        assert data["provider"] == "mock"


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_run_with_missing_goal_raises_via_handler(self):
        # The handler doesn't validate the schema (the MCP layer does), so
        # missing 'goal' results in a KeyError — caught by the wrapper.
        with pytest.raises(KeyError):
            await mcp_server._handle_run({})
