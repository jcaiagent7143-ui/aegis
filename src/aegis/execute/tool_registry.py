"""Tool registry — registers callables with JSON-schema metadata.

We deliberately keep the surface tiny: a `@tool(...)` decorator that attaches
metadata to a function, and a `ToolRegistry` that holds and filters them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aegis.providers.base import Tool as ProviderTool


@dataclass
class ToolSpec:
    """A registered tool: function plus discovery metadata."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    def to_provider_tool(self) -> ProviderTool:
        return ProviderTool(
            name=self.name,
            description=self.description,
            parameters_schema=self.parameters,
        )


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that tags a function as an Aegis tool."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__aegis_tool__ = ToolSpec(  # type: ignore[attr-defined]
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            fn=fn,
        )
        return fn

    return decorator


@dataclass
class ToolRegistry:
    """Holds the available tools; provides filtered views."""

    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, fn: Callable[..., Any]) -> None:
        spec = getattr(fn, "__aegis_tool__", None)
        if spec is None:
            raise ValueError(f"{fn} is not decorated with @tool(...)")
        self.tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self.tools)

    def get(self, name: str) -> ToolSpec | None:
        return self.tools.get(name)

    def subset(self, names: list[str]) -> ToolRegistry:
        """Return a registry containing only `names` (silently drops unknowns)."""
        return ToolRegistry(tools={n: self.tools[n] for n in names if n in self.tools})

    def catalog_for_prompt(self) -> str:
        """Compact human-readable summary for inclusion in synthesize/execute prompts."""
        lines: list[str] = []
        for spec in self.tools.values():
            lines.append(f"- {spec.name}: {spec.description}")
        return "\n".join(lines) or "(no tools)"


def default_registry() -> ToolRegistry:
    """Construct a registry with all built-in tools."""
    from aegis.tools import builtin

    reg = ToolRegistry()
    for name in dir(builtin):
        obj = getattr(builtin, name)
        if callable(obj) and hasattr(obj, "__aegis_tool__"):
            reg.register(obj)
    return reg
