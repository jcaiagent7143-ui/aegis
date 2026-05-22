"""MCP server implementation — exposes Aegis as tools to any MCP client.

Tools exposed:

  * ``aegis_run(goal, context?)`` — Full 5-stage pipeline. Returns the verified
    answer + a summary of the audit trail. THIS is the main one; calling it
    means "make this safe before I act on it."

  * ``aegis_assess(goal)`` — Just the risk-profile step. Cheap (one LLM call).
    Lets the outer AI decide whether to even attempt a risky task.

  * ``aegis_inspect(run_id)`` — Re-load a past audit trail. For debugging /
    compliance review.

  * ``aegis_list_risks()`` — Returns the 30-entry catalog so the outer AI knows
    what failure modes Aegis defends against.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from aegis import Aegis
from aegis.assess.risk_catalog import CATALOG

DEFAULT_CACHE_DIR = Path(os.environ.get("AEGIS_CACHE_DIR", ".aegis"))


def _make_aegis() -> Aegis:
    """Build an Aegis instance using whichever provider the env points to."""
    return Aegis(cache_dir=DEFAULT_CACHE_DIR)


# ── tool definitions (JSON-schema, used by the MCP wire protocol) ──────────

_AEGIS_RUN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "minLength": 1,
            "description": (
                "The task you want Aegis to perform under a self-generated "
                "safety harness. Examples: 'Compute the P/E of MSFT and show "
                "your work', 'List 3 OSS Python web frameworks with verified "
                "GitHub URLs', 'Verify ticket #11203 references a duplicate "
                "charge before issuing a refund'."
            ),
        },
        "context": {
            "type": "object",
            "description": "Optional extra context the agent may need.",
            "default": {},
        },
    },
    "required": ["goal"],
}

_AEGIS_ASSESS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string", "minLength": 1},
    },
    "required": ["goal"],
}

_AEGIS_INSPECT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "minLength": 1},
    },
    "required": ["run_id"],
}


# ── tool handlers ──────────────────────────────────────────────────────────


async def _handle_run(arguments: dict[str, Any]) -> str:
    aegis = _make_aegis()
    result = await aegis.run(
        goal=arguments["goal"],
        **(arguments.get("context") or {}),
    )
    return json.dumps(
        {
            "succeeded": result.audit.succeeded,
            "run_id": result.audit.run_id,
            "value": result.value,
            "harness_code": result.harness_code,
            "risks_identified": [
                {"id": r.id, "level": r.level.value, "rationale": r.rationale}
                for r in result.audit.risks.risks
            ],
            "repairs": result.audit.repairs,
            "tokens": result.audit.total_tokens,
            "tool_calls": [{"name": t["name"], "ok": t["ok"]} for t in result.audit.tool_calls],
            "provider": result.audit.provider,
            "cached": result.cached,
        },
        indent=2,
        default=str,
    )


async def _handle_assess(arguments: dict[str, Any]) -> str:
    from aegis.analyze import analyze
    from aegis.assess import assess
    from aegis.core.goal import Goal

    aegis = _make_aegis()
    goal = Goal(description=arguments["goal"])
    decomposition, _, _ = await analyze(goal, aegis.provider)
    risks, _, _ = await assess(goal, decomposition, aegis.provider)
    return json.dumps(
        {
            "summary": risks.summary(),
            "risks": [r.model_dump() for r in risks.risks],
            "invariants": risks.invariants,
            "suggested_tools": risks.suggested_tools,
            "forbidden_tools": risks.forbidden_tools,
        },
        indent=2,
        default=str,
    )


async def _handle_inspect(arguments: dict[str, Any]) -> str:
    aegis = _make_aegis()
    try:
        result = aegis.inspect(arguments["run_id"])
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(
        {
            "run_id": result.audit.run_id,
            "goal": result.audit.goal,
            "succeeded": result.audit.succeeded,
            "stages": [s.model_dump() for s in result.audit.stages],
            "harness_code": result.harness_code,
            "value": result.value,
        },
        indent=2,
        default=str,
    )


async def _handle_list_risks(_: dict[str, Any]) -> str:
    return json.dumps(
        {
            "catalog": [
                {
                    "id": e.id,
                    "name": e.name,
                    "description": e.description,
                    "typical_level": e.typical_level.value,
                    "trigger_keywords": list(e.trigger_keywords),
                    "defense_hints": list(e.defense_hints),
                }
                for e in CATALOG
            ],
            "count": len(CATALOG),
        },
        indent=2,
    )


def _build_server():
    """Construct the MCP Server with the four Aegis tools registered."""
    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server = Server("aegis")

    tools = [
        Tool(
            name="aegis_run",
            description=(
                "Run a task under an Aegis self-generated safety harness. "
                "Use this when about to take a risky or irreversible action — "
                "the LLM will design a per-task verifier, execute the work in "
                "a sandbox, and return a verified result (or refuse). Returns "
                "JSON with: succeeded, value, harness_code, risks_identified, "
                "repairs, tokens, run_id."
            ),
            inputSchema=_AEGIS_RUN_INPUT_SCHEMA,
        ),
        Tool(
            name="aegis_assess",
            description=(
                "Cheap risk-assessment-only mode (one LLM call). Returns the "
                "named failure modes that apply to this goal, without running "
                "the full pipeline. Use this to decide WHETHER to proceed with "
                "a risky task."
            ),
            inputSchema=_AEGIS_ASSESS_INPUT_SCHEMA,
        ),
        Tool(
            name="aegis_inspect",
            description=(
                "Re-load a saved audit trail for a past Aegis run. For "
                "compliance review and debugging."
            ),
            inputSchema=_AEGIS_INSPECT_INPUT_SCHEMA,
        ),
        Tool(
            name="aegis_list_risks",
            description=(
                "Return the Aegis risk catalog — the 30+ named failure modes "
                "Aegis knows how to defend against. Read this once to learn "
                "what protections are available."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    handlers = {
        "aegis_run": _handle_run,
        "aegis_assess": _handle_assess,
        "aegis_inspect": _handle_inspect,
        "aegis_list_risks": _handle_list_risks,
    }

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        handler = handlers.get(name)
        if handler is None:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            text = await handler(arguments or {})
        except Exception as e:
            text = json.dumps({"error": f"{type(e).__name__}: {e}"})
        return [TextContent(type="text", text=text)]

    return server


async def _serve_stdio() -> None:
    from mcp.server.stdio import stdio_server

    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run() -> None:
    """Blocking entrypoint — what ``aegis mcp`` calls."""
    import contextlib

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve_stdio())


if __name__ == "__main__":
    run()
