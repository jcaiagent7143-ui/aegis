"""Stage 4 — Execute: run the agent loop inside the synthesized harness."""

from aegis.execute.runner import execute
from aegis.execute.tool_registry import ToolRegistry, default_registry, tool

__all__ = ["ToolRegistry", "default_registry", "execute", "tool"]
