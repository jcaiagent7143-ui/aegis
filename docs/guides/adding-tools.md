# Adding tools

A tool is just a regular Python function with a thin metadata wrapper.

## Minimal example

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
