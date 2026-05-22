"""The Aegis facade — the single entrypoint everyone uses."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aegis.core.goal import Goal
from aegis.core.result import Result

if TYPE_CHECKING:
    from aegis.execute.tool_registry import ToolRegistry
    from aegis.memory.harness_cache import HarnessCache
    from aegis.providers.base import Provider


class Aegis:
    """Public entrypoint for self-harnessing agent execution.

    >>> aegis = Aegis()                       # auto-detect provider from env
    >>> result = await aegis.run("...")       # doctest: +SKIP

    Parameters
    ----------
    provider:
        LLM provider. If omitted, picks the first env-configured one in this
        order: Anthropic, OpenAI, Ollama. Pass a provider explicitly to override.
    tools:
        Optional ToolRegistry. If omitted, the default registry of built-in
        safe tools is used (web_search, fetch_url, read_file, run_python, ...).
    cache_dir:
        Directory where audit trails and the harness cache live.
        Defaults to ``.aegis/`` in the cwd.
    max_repairs:
        Optional override of each harness's own ``MAX_REPAIRS`` value. If None
        (default), every task uses whatever its synthesized harness declared.
        Pass an int to force a global ceiling regardless of harness.
    enable_cache:
        Whether to consult and write to the harness cache.
    """

    def __init__(
        self,
        provider: Provider | None = None,
        *,
        tools: ToolRegistry | None = None,
        cache_dir: str | Path | None = None,
        max_repairs: int | None = None,
        enable_cache: bool = True,
    ) -> None:
        from aegis.execute.tool_registry import default_registry
        from aegis.memory.harness_cache import HarnessCache
        from aegis.providers import auto_provider

        self.provider: Provider = provider or auto_provider()
        self.tools: ToolRegistry = tools or default_registry()
        self.cache_dir = Path(cache_dir or ".aegis").resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_repairs = max_repairs
        self.enable_cache = enable_cache
        self.cache: HarnessCache = HarnessCache(self.cache_dir / "harnesses")

    async def run(self, goal: str | Goal, **context: Any) -> Result:
        """Run the full 5-stage pipeline on a goal."""
        from aegis.core.pipeline import Pipeline

        goal_obj = goal if isinstance(goal, Goal) else Goal(description=goal, context=context)
        pipeline = Pipeline(
            provider=self.provider,
            tools=self.tools,
            cache=self.cache if self.enable_cache else None,
            max_repairs=self.max_repairs,
        )
        result = await pipeline.execute(goal_obj)
        # Persist the audit trail
        result.audit.save(self.cache_dir / "runs" / f"{result.audit.run_id}.json")
        return result

    def inspect(self, run_id: str) -> Result:
        """Load a past run's audit trail and reconstruct the Result."""
        from aegis.core.result import AuditTrail

        path = self.cache_dir / "runs" / f"{run_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"No run with id {run_id} in {self.cache_dir}")
        audit = AuditTrail.load(path)
        # value isn't durably stored as typed — return the raw value from the execute stage
        execute_stage = audit.stage("execute")
        value = execute_stage.output.get("value") if execute_stage else None
        return Result(value=value, harness_code=audit.harness_code, audit=audit)

    async def replay(self, run_id: str) -> Result:
        """Re-execute against a saved harness (skips stages 1-3)."""
        from aegis.core.pipeline import Pipeline

        past = self.inspect(run_id)
        goal_obj = Goal(description=past.audit.goal)
        pipeline = Pipeline(
            provider=self.provider,
            tools=self.tools,
            cache=None,
            max_repairs=self.max_repairs,
        )
        result = await pipeline.replay(
            goal_obj, harness_code=past.harness_code, risks=past.audit.risks
        )
        result.audit.save(self.cache_dir / "runs" / f"{result.audit.run_id}.json")
        return result
