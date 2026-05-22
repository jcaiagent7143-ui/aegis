"""Example 06 — Use existing LangChain tools as Aegis tools.

Aegis tools are plain functions decorated with ``@tool(...)``. Wrap any
LangChain BaseTool into that shape and Aegis will treat it the same as a
built-in tool.

Install: ``pip install self-harness langchain-community``
"""

from __future__ import annotations

import asyncio
from typing import Any

from aegis import Aegis
from aegis.execute.tool_registry import default_registry, tool


def wrap_langchain_tool(lc_tool: Any) -> Any:
    """Adapter from a LangChain BaseTool to an Aegis-decorated function."""

    @tool(
        name=lc_tool.name,
        description=lc_tool.description,
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    def adapted(query: str) -> Any:
        return lc_tool.invoke(query)

    return adapted


async def main() -> None:
    try:
        from langchain_community.tools import DuckDuckGoSearchRun  # type: ignore[import-not-found]
    except ImportError:
        print("This example needs `pip install langchain-community`. Skipping.")
        return

    lc_tool = DuckDuckGoSearchRun()
    registry = default_registry()
    registry.register(wrap_langchain_tool(lc_tool))

    aegis = Aegis(tools=registry)
    result = await aegis.run("What is the current LangChain release version?")
    print(result.to_json())


if __name__ == "__main__":
    asyncio.run(main())
