"""The built-in tool set.

Every tool is a regular sync function decorated with ``@tool(...)``.
The decorator attaches JSON-schema metadata used by the executor and providers.

Tools are intentionally conservative: file access stays within a workspace,
network calls have timeouts, no shell, no `subprocess`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from aegis.execute.tool_registry import tool

DEFAULT_TIMEOUT = 10.0
MAX_BYTES_READ = 200_000


def _workspace() -> Path:
    return Path(os.environ.get("AEGIS_WORKSPACE", os.getcwd())).resolve()


def _safe_path(p: str | Path) -> Path:
    ws = _workspace()
    abs_p = (ws / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    try:
        abs_p.relative_to(ws)
    except ValueError as e:
        raise PermissionError(f"Path {abs_p} is outside workspace {ws}") from e
    return abs_p


@tool(
    name="fetch_url",
    description="HTTP GET a URL, returning {status_code, text (truncated), headers}.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "uri"},
            "timeout": {"type": "number", "minimum": 0.1, "maximum": 30, "default": 10},
        },
        "required": ["url"],
    },
)
def fetch_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """GET a URL. Truncates body to MAX_BYTES_READ."""
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as c:
            r = c.get(url)
            body = r.text
            if len(body) > MAX_BYTES_READ:
                body = body[:MAX_BYTES_READ] + f"\n…[truncated, {len(r.text)} bytes total]"
            return {
                "status_code": r.status_code,
                "text": body,
                "headers": dict(r.headers),
                "url": str(r.url),
            }
    except httpx.HTTPError as e:
        return {"status_code": 0, "text": "", "error": str(e), "url": url}


@tool(
    name="web_search",
    description="Search the web for a query (uses DuckDuckGo's HTML endpoint).",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Lightweight DuckDuckGo HTML scrape.

    Returns a list of {title, url, snippet}. If the network is unavailable,
    returns an empty list rather than raising — the agent should treat empty as
    "no results found" and proceed accordingly.
    """
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as c:
            r = c.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Aegis/0.1 (+https://github.com/aegis-harness)"},
            )
    except httpx.HTTPError:
        return []

    if r.status_code != 200:
        return []

    # Minimal HTML parsing — keep dependency-free
    import re

    items: list[dict[str, str]] = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'(?:.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
        r.text,
        re.DOTALL,
    ):
        url = _clean_text(m.group(1))
        title = _clean_text(m.group(2) or "")
        snippet = _clean_text(m.group(3) or "")
        items.append({"title": title, "url": url, "snippet": snippet})
        if len(items) >= max_results:
            break
    return items


def _clean_text(s: str) -> str:
    import re

    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").strip()


@tool(
    name="read_file",
    description="Read a UTF-8 text file from the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1_000_000, "default": 200000},
        },
        "required": ["path"],
    },
)
def read_file(path: str, max_bytes: int = MAX_BYTES_READ) -> str:
    p = _safe_path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    data = p.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


@tool(
    name="write_file",
    description="Write UTF-8 text to a file in the workspace (creates dirs).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> dict[str, Any]:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes": len(content.encode("utf-8"))}


@tool(
    name="list_dir",
    description="List entries in a directory under the workspace.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "default": "."}},
    },
)
def list_dir(path: str = ".") -> list[str]:
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(p)
    return sorted(e.name for e in p.iterdir())


@tool(
    name="run_python_snippet",
    description=(
        "Execute a short, self-contained Python snippet in a restricted namespace. "
        "Use for arithmetic, CSV/JSON parsing, regex, simple data manipulation. "
        "Returns the value bound to `result` in the snippet (or None)."
    ),
    parameters={
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
)
def run_python_snippet(code: str) -> Any:
    """Execute Python in a restricted namespace; returns the value of `result`."""
    from aegis.synthesize.sandbox import _safe_builtins, validate_source

    validate_source(code)  # reuse the same AST guard
    namespace: dict[str, Any] = {
        "__name__": "_aegis_snippet",
        "__builtins__": _safe_builtins(),
        "result": None,
    }
    # Add commonly-needed safe modules
    import json as _json
    import math as _math
    import re as _re
    import statistics as _stats

    namespace.update({"json": _json, "math": _math, "re": _re, "statistics": _stats})

    exec(compile(code, "<aegis-snippet>", "exec"), namespace)
    return namespace.get("result")
