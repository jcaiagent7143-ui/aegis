# Adding tools

A tool is just a regular Python function with a thin metadata wrapper.

## Recommended first replacement: swap the built-in `web_search`

The built-in `web_search` is a DuckDuckGo HTML scrape that ships so the
package works zero-config. It's NOT production-grade — DuckDuckGo
rate-limits aggressively and returns sparse results for time-sensitive or
specific queries. External testing showed this is the most common cause of
`succeeded=false` on research-style goals: the strict synthesized harness
can't find verifiable sources because `web_search` returned nothing.

Swap it for any real search API. Register a tool with the same name and
Aegis picks the last-registered version. Examples below — pick one based
on which API key you have.

### Tavily (recommended for general research)

```python
import os
from tavily import TavilyClient
from aegis.execute.tool_registry import default_registry, tool

_tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

@tool(
    name="web_search",
    description="High-quality web search with relevance ranking.",
    parameters={"type": "object",
                "properties": {"query": {"type": "string"},
                               "max_results": {"type": "integer", "default": 5}},
                "required": ["query"]},
)
def web_search(query: str, max_results: int = 5):
    return _tavily.search(query, max_results=max_results)["results"]

registry = default_registry()
registry.register(web_search)   # overrides the built-in
```

### Brave Search

```python
import httpx, os
from aegis.execute.tool_registry import default_registry, tool

@tool(
    name="web_search",
    description="Brave Search API.",
    parameters={"type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]},
)
def web_search(query: str, max_results: int = 5):
    r = httpx.get("https://api.search.brave.com/res/v1/web/search",
                  params={"q": query, "count": max_results},
                  headers={"X-Subscription-Token": os.environ["BRAVE_API_KEY"]})
    r.raise_for_status()
    return [{"title": x["title"], "url": x["url"], "snippet": x["description"]}
            for x in r.json()["web"]["results"]]

registry = default_registry()
registry.register(web_search)
```

### Perplexity, Exa, You.com

Same pattern — wrap their HTTP client, register under `name="web_search"`,
Aegis uses it. Aegis only cares that the tool returns a list of dicts with
`{title, url, snippet}` so the synthesized verifier can iterate over them.

---

## The general pattern (any tool)

## Minimal example for any other tool

```python
from aegis.execute.tool_registry import default_registry, tool

@tool(
    name="hash_sha256",
    description="Return the hex SHA-256 of a string.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def hash_sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()

registry = default_registry()
registry.register(hash_sha256)
```

Pass it in:

```python
from aegis import Aegis
aegis = Aegis(tools=registry)
```

Now the synthesizer can include `"hash_sha256"` in `ALLOWED_TOOLS` and the agent (or the `verify()` function) can call it.

## Conventions

- **Names** are snake_case and globally unique inside a registry.
- **Descriptions** are one sentence, action-first ("Return the hex SHA-256 of a string.").
- **Parameters** use JSON-schema. Be specific about types and bounds — the model uses these to call your tool correctly.
- **Return values** must be JSON-serializable (the executor logs them to the audit trail).
- **Exceptions** are caught by the executor and surfaced as `ok: False` tool outcomes. Raise meaningful messages.

## Async tools

The executor uses `asyncio.to_thread()` to run sync tools off the event loop, so most tools can stay synchronous. If you need true async, await in your handler — Aegis will call it via `await` automatically (planned for v0.2).

## Workspace-safe file access

If your tool reads or writes files, use `aegis.tools.builtin._safe_path` (or write your own equivalent) to constrain access to `AEGIS_WORKSPACE` (defaults to cwd). Otherwise the `path-traversal` risk in the catalog will (rightly) flag your tool as overscoped.
