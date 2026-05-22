"""Sandbox for executing model-generated harness code.

Two layers of defense:

  1. **Static AST validation** — reject forbidden nodes, imports, names, and
     attribute accesses before the source ever runs.
  2. **Restricted exec** — load the module with a curated ``__builtins__``
     allowlist; pre-bind only the modules we want (pydantic, re, math, json,
     plus the ``tool(name, **kwargs)`` helper).

For the ``verify()`` call itself we additionally enforce a wall-clock timeout
and (on Unix) a soft memory cap via ``resource.setrlimit`` plus
``signal.SIGALRM``. This stops a confused-or-malicious harness from hanging
the host process or eating all RAM.

This is not a hardened security boundary suitable for adversarial multi-tenant
hosting — for that, run aegis inside its own process namespace (firejail,
Docker, gVisor). But it stops the realistic foot-guns (rm -rf, exfiltration
via sockets, infinite loops, OOM) cleanly and predictably.
"""

from __future__ import annotations

import ast
import json
import math
import re
import signal
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pydantic

# Modules the generated harness may `import` (top-level or `from X import ...`).
ALLOWED_IMPORTS = frozenset(
    {
        "pydantic",
        "typing",
        "re",
        "math",
        "json",
        "datetime",
        "decimal",
        "enum",
        # `aegis.tools` is special-cased — we don't expose the real module, only
        # the `tool` helper. But we tolerate the import line for ergonomics.
        "aegis.tools",
    }
)

# AST node types that are flat-out denied.
FORBIDDEN_NODES = (
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.Await,
)

# Names the generated code may NOT reference.
FORBIDDEN_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "exit",
        "quit",
        "breakpoint",
        "help",
        "memoryview",
        "__builtins__",
        "__loader__",
        "__spec__",
        "__package__",
    }
)

# Attribute access patterns that smell dangerous.
FORBIDDEN_ATTRS = frozenset(
    {
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__code__",
        "__getattribute__",
        "__import__",
        "__builtins__",
        "__dict__",
    }
)


class SandboxError(Exception):
    """Raised when generated code fails validation or execution."""


DEFAULT_SYSTEM_PROMPT = (
    "You are an AI agent operating inside an Aegis-generated harness. "
    "Use the allowed tools to gather what you need, then emit a single JSON "
    "object matching the schema. Reply with raw JSON only — no prose, no "
    "markdown fences. If a tool errors, surface that in your answer rather "
    "than pretending it succeeded."
)


@dataclass
class HarnessModule:
    """A loaded, validated harness module — the *complete* runtime spec.

    Versus v0.2, this carries not just the safety layer (Output, ALLOWED_TOOLS,
    verify) but the entire agent runtime configuration (system prompt, loop
    budget, retry policy, tool description overrides, repair feedback). The
    executor is now a thin interpreter of whatever fields this module defines.
    """

    source: str
    output_model: type[pydantic.BaseModel]
    allowed_tools: list[str]
    verify_fn: Callable[..., list[str]]
    raw_namespace: dict[str, Any] = field(default_factory=dict)

    # ── new v0.3 fields — every one optional, with safe defaults ──
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_steps: int = 8
    max_repairs: int = 1
    max_tokens_per_turn: int = 2048
    temperature: float = 0.0
    tool_overrides: dict[str, str] = field(default_factory=dict)
    repair_feedback_fn: Callable[..., str] | None = None

    def validate_output(self, data: Any) -> pydantic.BaseModel:
        """Validate a candidate output dict against the synthesized Output model."""
        if isinstance(data, self.output_model):
            return data
        if isinstance(data, dict):
            return self.output_model.model_validate(data)
        # If the model returned a string, try to parse JSON
        if isinstance(data, str):
            try:
                return self.output_model.model_validate_json(data)
            except pydantic.ValidationError:
                pass
        raise SandboxError(
            f"Output is not coercible into {self.output_model.__name__}: {type(data)}"
        )

    def call_verify(
        self,
        output: pydantic.BaseModel,
        *,
        timeout_s: float = 10.0,
        memory_mb: int | None = 512,
    ) -> list[str]:
        """Run ``verify(output)`` under wall-clock + memory limits."""
        return run_with_limits(
            lambda: self.verify_fn(output),
            timeout_s=timeout_s,
            memory_mb=memory_mb,
        )

    def repair_feedback(self, failures: list[str], output: Any) -> str:
        """Compose the user-message fed back to the model on a verify failure.

        Uses the harness's own ``repair_feedback`` function if defined; otherwise
        a sensible default.
        """
        if self.repair_feedback_fn is not None:
            try:
                result = self.repair_feedback_fn(failures, output)
                if isinstance(result, str) and result:
                    return result
            except Exception:
                pass  # fall through to default
        joined = "; ".join(failures) if failures else "(unspecified)"
        return (
            f"Your previous answer failed verification: {joined}. "
            "Address each failure in your next answer; re-fetch any tool data "
            "you cited. Reply with raw JSON only."
        )


class SandboxTimeout(SandboxError):
    """Raised when verify() exceeds its wall-clock budget."""


def run_with_limits(
    fn: Callable[[], Any],
    *,
    timeout_s: float = 10.0,
    memory_mb: int | None = 512,
) -> Any:
    """Run a zero-arg callable with a wall-clock and memory cap.

    Uses ``signal.SIGALRM`` for timeout and ``resource.setrlimit(RLIMIT_AS)``
    for the memory cap. Limitations:

      * **POSIX only**. On Windows we fall back to no enforcement.
      * **Main thread only**. ``signal.signal`` raises ``ValueError`` outside
        the main thread (asyncio thread pools, FastAPI/uvicorn workers,
        celery tasks, …). In those contexts we fall back to no enforcement
        rather than crashing the caller; callers running untrusted code in
        background threads should add their own out-of-process isolation.
    """
    import threading

    not_main_thread = threading.current_thread() is not threading.main_thread()
    if sys.platform == "win32" or signal is None or not_main_thread:
        if not_main_thread:
            sys.stderr.write("[aegis] WARNING: sandbox limits not enforced in background thread\n")
        return fn()

    import resource

    prev_handler = signal.getsignal(signal.SIGALRM)

    def _on_timeout(signum: int, frame: Any) -> None:
        raise SandboxTimeout(f"verify() exceeded {timeout_s}s wall-clock")

    prev_mem: tuple[int, int] | None = None
    if memory_mb is not None:
        try:
            prev_mem = resource.getrlimit(resource.RLIMIT_AS)
            cap = memory_mb * 1024 * 1024
            # Don't raise above the existing hard limit
            hard = prev_mem[1] if prev_mem[1] > 0 else cap
            resource.setrlimit(resource.RLIMIT_AS, (min(cap, hard), hard))
        except (ValueError, OSError):
            prev_mem = None  # platform refused; carry on without

    signal.signal(signal.SIGALRM, _on_timeout)
    # ITIMER_REAL gives sub-second precision unlike signal.alarm()
    signal.setitimer(signal.ITIMER_REAL, max(0.001, timeout_s))
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prev_handler)
        if prev_mem is not None:
            import contextlib

            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(resource.RLIMIT_AS, prev_mem)


def validate_source(source: str) -> None:
    """Parse and walk the AST, rejecting anything dangerous. Raises SandboxError."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as e:
        raise SandboxError(f"Generated harness has a syntax error: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise SandboxError(f"Forbidden construct: {type(node).__name__} at line {node.lineno}")

        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS and not _allowed_subimport(alias.name):
                    raise SandboxError(f"Forbidden import: {alias.name}")

        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod not in ALLOWED_IMPORTS and not _allowed_subimport(mod):
                raise SandboxError(f"Forbidden import from: {mod}")

        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"Forbidden name reference: {node.id} at line {node.lineno}")

        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            raise SandboxError(f"Forbidden attribute access: .{node.attr} at line {node.lineno}")

        # Detect getattr() with first arg looking like a sandbox bypass attempt
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("getattr", "setattr", "delattr")
        ):
            raise SandboxError(f"{node.func.id}() is not allowed in harness code")


def _allowed_subimport(module: str) -> bool:
    """Allow dotted children of allowed top-level modules (e.g. typing.Literal)."""
    head = module.split(".", 1)[0]
    return head in {m.split(".", 1)[0] for m in ALLOWED_IMPORTS}


# Curated builtin allowlist — minimal but enough for typical schema/verifier code.
def _safe_builtins() -> dict[str, Any]:
    import builtins as _b

    allowed = {
        # Types & constructors
        "bool",
        "bytes",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "object",
        "set",
        "str",
        "tuple",
        "type",
        "bytearray",
        # Iteration & functional
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "reversed",
        "sorted",
        "sum",
        "min",
        "max",
        "any",
        "all",
        "abs",
        "round",
        "next",
        "iter",
        # Identity / repr
        "isinstance",
        "issubclass",
        "id",
        "hash",
        "repr",
        "ascii",
        "chr",
        "ord",
        "hex",
        "bin",
        "oct",
        "divmod",
        "pow",
        # Misc safe
        "print",  # captured into a list, see below
        "True",
        "False",
        "None",
        # Exceptions
        "Exception",
        "ValueError",
        "TypeError",
        "AssertionError",
        "KeyError",
        "IndexError",
        "StopIteration",
        "RuntimeError",
        "NotImplementedError",
        "ZeroDivisionError",
        "AttributeError",
        "LookupError",
        "ArithmeticError",
        "OverflowError",
        "FloatingPointError",
        # Class machinery the user might transitively need
        "classmethod",
        "staticmethod",
        "property",
        "super",
        # Slice & format
        "slice",
        "format",
    }
    out = {name: getattr(_b, name) for name in allowed if hasattr(_b, name)}
    # `__import__` is needed by Python's `import` statement machinery itself.
    # We DON'T expose it as a name (AST blocks `__import__("os")`) — we just
    # let import statements work via the validated ALLOWED_IMPORTS allowlist.
    out["__import__"] = _b.__import__
    # `__build_class__` is required by the `class` statement machinery.
    out["__build_class__"] = _b.__build_class__
    return out


def load_harness(
    source: str,
    *,
    tool_callable: Callable[..., Any] | None = None,
) -> HarnessModule:
    """Validate, exec, and bind the generated harness.

    Parameters
    ----------
    source:
        The Python source from the synthesize stage.
    tool_callable:
        Function exposed to the harness as ``tool(name, **kwargs)``. If omitted,
        a stub that raises is installed (useful for validation-only loads).
    """
    validate_source(source)

    if tool_callable is None:

        def _stub_tool(name: str, **_kwargs: Any) -> Any:
            raise SandboxError(f"Tool '{name}' called but no tool runtime was bound.")

        tool_callable = _stub_tool

    namespace: dict[str, Any] = {
        "__name__": "_aegis_harness",
        "__builtins__": _safe_builtins(),
        # Pre-imported modules so the harness can reference them even without import
        "pydantic": pydantic,
        "re": re,
        "math": math,
        "json": json,
        # The tool helper — generated `verify` may call this
        "tool": tool_callable,
        # Convenience: a no-op for top-level `aegis.tools` references
        "aegis": types.SimpleNamespace(tools=types.SimpleNamespace()),
    }

    # Patch typing.Literal etc. to be importable — typing is in ALLOWED_IMPORTS
    # so the generated `from typing import ...` will work via the real import system.
    try:
        compiled = compile(source, "<aegis-harness>", "exec")
        exec(compiled, namespace)
    except SandboxError:
        raise
    except Exception as e:
        raise SandboxError(f"Generated harness raised during definition: {e}") from e

    # ── REQUIRED: Output, ALLOWED_TOOLS, verify ─────────────────────────
    out_model = namespace.get("Output")
    if not (isinstance(out_model, type) and issubclass(out_model, pydantic.BaseModel)):
        raise SandboxError("Generated harness did not define class `Output(pydantic.BaseModel)`")

    # Pydantic v2 stores annotations as strings (PEP 563) for dynamically-exec'd
    # classes and resolves them later via the class's `__module__` namespace.
    # Our synthetic module name doesn't exist in sys.modules, so `Any`, `Literal`,
    # custom types, etc. won't resolve. Rebuild against the harness namespace so
    # everything in scope at class definition is visible to validators.
    try:
        out_model.model_rebuild(_types_namespace=namespace, force=True)
    except pydantic.PydanticUndefinedAnnotation as e:
        raise SandboxError(f"Output model has unresolved type annotation: {e}") from e
    except Exception as e:
        raise SandboxError(f"Output.model_rebuild failed: {e}") from e

    allowed_raw = namespace.get("ALLOWED_TOOLS", [])
    if not isinstance(allowed_raw, list) or not all(isinstance(x, str) for x in allowed_raw):
        raise SandboxError("Generated harness did not define `ALLOWED_TOOLS: list[str]`")
    allowed: list[str] = list(allowed_raw)

    verify_fn = namespace.get("verify")
    if not callable(verify_fn):
        raise SandboxError("Generated harness did not define `def verify(output) -> list[str]`")

    # ── OPTIONAL: harness-runtime config (v0.3) ────────────────────────
    system_prompt = _coerce_str(namespace.get("SYSTEM_PROMPT"), DEFAULT_SYSTEM_PROMPT)
    max_steps = _coerce_int(namespace.get("MAX_STEPS"), 8, lo=1, hi=50)
    max_repairs = _coerce_int(namespace.get("MAX_REPAIRS"), 1, lo=0, hi=5)
    max_tokens_per_turn = _coerce_int(namespace.get("MAX_TOKENS_PER_TURN"), 2048, lo=64, hi=16384)
    temperature = _coerce_float(namespace.get("TEMPERATURE"), 0.0, lo=0.0, hi=2.0)
    tool_overrides_raw = namespace.get("TOOL_OVERRIDES", {})
    tool_overrides: dict[str, str] = {}
    if isinstance(tool_overrides_raw, dict):
        for k, v in tool_overrides_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                tool_overrides[k] = v
    repair_fn = namespace.get("repair_feedback")
    if not callable(repair_fn):
        repair_fn = None

    return HarnessModule(
        source=source,
        output_model=out_model,
        allowed_tools=allowed,
        verify_fn=verify_fn,
        raw_namespace=namespace,
        system_prompt=system_prompt,
        max_steps=max_steps,
        max_repairs=max_repairs,
        max_tokens_per_turn=max_tokens_per_turn,
        temperature=temperature,
        tool_overrides=tool_overrides,
        repair_feedback_fn=repair_fn,
    )


def _coerce_str(v: Any, default: str) -> str:
    return v if isinstance(v, str) and v.strip() else default


def _coerce_int(v: Any, default: int, *, lo: int, hi: int) -> int:
    if isinstance(v, bool):  # bool is a subclass of int — reject explicitly
        return default
    if isinstance(v, int):
        return max(lo, min(hi, v))
    return default


def _coerce_float(v: Any, default: float, *, lo: float, hi: float) -> float:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(lo, min(hi, float(v)))
    return default
