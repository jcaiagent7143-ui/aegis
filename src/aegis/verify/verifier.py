"""Stage 5 — Verify: invoke the synthesized verifier function under limits."""

from __future__ import annotations

from typing import Any

from aegis.execute.tool_registry import ToolRegistry
from aegis.synthesize.sandbox import HarnessModule, SandboxError, SandboxTimeout


def verify(
    output_value: Any,
    harness: HarnessModule,
    tools: ToolRegistry,
    *,
    timeout_s: float = 10.0,
    memory_mb: int | None = 512,
) -> list[str]:
    """Run the synthesized ``verify(output)`` under wall-clock + memory limits.

    Returns a list of failure messages. Empty list means verification passed.
    The verifier is allowed to call tools via the ``tool(name, **kwargs)``
    helper injected into the harness namespace.
    """
    try:
        validated = harness.validate_output(output_value)
    except SandboxError as e:
        return [f"output failed schema validation: {e}"]

    # Re-bind the `tool` helper so verify() can call live tools
    def _tool(name: str, **kwargs: Any) -> Any:
        spec = tools.get(name)
        if spec is None:
            raise SandboxError(f"verify() called unknown tool '{name}'")
        return spec.fn(**kwargs)

    harness.raw_namespace["tool"] = _tool

    try:
        result = harness.call_verify(validated, timeout_s=timeout_s, memory_mb=memory_mb)
    except SandboxTimeout as e:
        return [str(e)]
    except Exception as e:
        return [f"verify() raised {type(e).__name__}: {e}"]

    if not isinstance(result, list):
        return [f"verify() returned {type(result).__name__}, expected list[str]"]
    return [str(x) for x in result]
