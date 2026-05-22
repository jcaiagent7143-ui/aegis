"""Aegis as a Model Context Protocol server.

Exposes the Aegis pipeline as MCP tools that any MCP-compatible AI assistant
(Claude Code, Cursor, Cline, Continue, Windsurf, …) can call.

Run with::

    aegis mcp                       # stdio transport (the MCP standard)
    uvx self-harness mcp           # zero-install

Then add to the client's MCP config (e.g. ``~/.claude/mcp.json``)::

    {
      "mcpServers": {
        "aegis": {
          "command": "uvx",
          "args": ["self-harness", "mcp"]
        }
      }
    }

The client's LLM now has four tools available: ``aegis_run``, ``aegis_assess``,
``aegis_inspect``, ``aegis_list_risks``. See ``src/aegis/mcp/server.py``.
"""

from aegis.mcp.server import run as run_stdio

__all__ = ["run_stdio"]
