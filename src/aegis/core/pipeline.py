"""The 5-stage Aegis pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.analyze import analyze
from aegis.assess import assess
from aegis.core.goal import Goal
from aegis.core.result import AuditTrail, Result, StageRecord
from aegis.core.risk import RiskProfile
from aegis.execute import execute
from aegis.execute.tool_registry import ToolRegistry
from aegis.memory.harness_cache import HarnessCache
from aegis.providers.base import Provider
from aegis.synthesize import load_harness, synthesize
from aegis.synthesize.sandbox import SandboxError
from aegis.verify import verify as verify_stage


class Pipeline:
    """Runs the 5 stages: analyze → assess → synthesize → execute → verify (→ repair)."""

    def __init__(
        self,
        provider: Provider,
        tools: ToolRegistry,
        cache: HarnessCache | None = None,
        *,
        max_repairs: int | None = None,
        audit_path: Path | None = None,
    ) -> None:
        """Create a pipeline.

        Parameters
        ----------
        max_repairs:
            Optional override of the per-harness ``MAX_REPAIRS``. If None
            (default), each task uses whatever ``MAX_REPAIRS`` its synthesized
            harness declared (or the harness default, 1). Pass an int here
            only to force a global ceiling regardless of harness.
        audit_path:
            Optional path the pipeline will incrementally write the audit
            trail to after every stage. If ``None``, no incremental persistence
            (the caller can still ``audit.save(...)`` at the end). When set,
            a crash mid-pipeline leaves a recoverable partial JSON on disk
            showing exactly which stages completed.
        """
        self.provider = provider
        self.tools = tools
        self.cache = cache
        self.max_repairs_override = max_repairs
        self.audit_path = audit_path

    def _persist(self, audit: AuditTrail) -> None:
        """Atomically write the audit JSON if a path was configured.

        Atomic = write to ``<path>.partial`` then rename. A reader who sees
        ``<path>.partial`` knows a run is in flight; a reader who sees
        ``<path>`` sees a stage-consistent snapshot.
        """
        if self.audit_path is None:
            return
        try:
            from pathlib import Path

            target = Path(self.audit_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".partial")
            tmp.write_text(audit.model_dump_json(indent=2))
            tmp.replace(target)
        except Exception:
            # Persistence must never break the pipeline itself.
            pass

    async def execute(self, goal: Goal) -> Result:
        audit = AuditTrail(goal=goal.description, provider=self.provider.name)
        self._persist(audit)  # write the empty shell so partial state exists
        # Cache lookups are only safe when the *current* provider is real.
        # If we're on Mock (no API key), don't trust cache hits either —
        # the user is probably probing, not running for keeps.
        cache_safe = self.cache is not None and not self._provider_is_mock()
        cached = (
            self.cache.lookup(goal.description) if cache_safe and self.cache is not None else None
        )

        if cached:
            audit.harness_code = cached.harness_code
            audit.risks = cached.risks
            stage = StageRecord(name="cache_hit", output={"hash": cached.hash})
            stage.mark_finished(notes=f"reused harness {cached.hash}")
            audit.stages.append(stage)
            self._persist(audit)
            if self.cache is not None:
                self.cache.record_hit(cached.hash)
            return await self._run_with_harness(
                goal, cached.harness_code, cached.risks, audit, cached=True
            )

        # 1 — ANALYZE
        stage = StageRecord(name="analyze")
        decomposition, ti, to = await analyze(goal, self.provider)
        stage.output = decomposition
        stage.tokens_in, stage.tokens_out = ti, to
        stage.mark_finished()
        audit.stages.append(stage)
        self._persist(audit)

        # 2 — ASSESS
        stage = StageRecord(name="assess")
        risks, ti, to = await assess(goal, decomposition, self.provider)
        stage.output = {"profile": risks.model_dump()}
        stage.tokens_in, stage.tokens_out = ti, to
        stage.mark_finished()
        audit.stages.append(stage)
        audit.risks = risks
        self._persist(audit)

        # 3 — SYNTHESIZE
        stage = StageRecord(name="synthesize")
        catalog = self.tools.catalog_for_prompt()
        source, ti, to = await synthesize(goal, decomposition, risks, catalog, self.provider)
        stage.output = {"source_preview": source[:400]}
        stage.tokens_in, stage.tokens_out = ti, to
        stage.mark_finished()
        audit.stages.append(stage)
        audit.harness_code = source
        self._persist(audit)

        # Run the synthesized harness FIRST, then only cache it if the run
        # actually succeeded with a real provider. Caching before execution
        # poisoned the cache with broken or Mock-fallback harnesses that
        # later sessions would silently replay (the bug in v0.5.3 e2e test).
        result = await self._run_with_harness(goal, source, risks, audit, cached=False)
        if self.cache is not None and result.audit.succeeded and not self._provider_is_mock():
            self.cache.put(goal.description, source, risks)
        return result

    def _provider_is_mock(self) -> bool:
        """True only if the Mock provider was selected as an auto-fallback.

        Explicit `provider=Mock(...)` instances used in unit tests are NOT
        flagged — they're a legitimate testing surface and the cache should
        work normally for them. Only the auto-fallback case (user set
        OPENAI_API_KEY but didn't install `[openai]`) is suspect, because
        the returned `[mock] ...` text would otherwise poison the cache
        for the next real-provider session.
        """
        return bool(getattr(self.provider, "_is_auto_fallback", False))

    async def replay(
        self,
        goal: Goal,
        *,
        harness_code: str,
        risks: RiskProfile,
    ) -> Result:
        audit = AuditTrail(goal=goal.description, provider=self.provider.name)
        audit.harness_code = harness_code
        audit.risks = risks
        return await self._run_with_harness(goal, harness_code, risks, audit, cached=True)

    # ── execute + verify (+ repair) ───────────────────────────────────────

    async def _run_with_harness(
        self,
        goal: Goal,
        source: str,
        risks: RiskProfile,
        audit: AuditTrail,
        *,
        cached: bool,
    ) -> Result:
        # Load harness with the live tool runtime
        def _tool_runtime(name: str, **kwargs: Any) -> Any:
            spec = self.tools.get(name)
            if spec is None:
                raise SandboxError(f"Tool '{name}' not registered")
            return spec.fn(**kwargs)

        # If the synthesized source fails to load (e.g. pydantic schema bug
        # the synthesizer's own retry loop didn't catch), fall back to the
        # deterministic template so the pipeline never crashes on the user.
        try:
            harness = load_harness(source, tool_callable=_tool_runtime)
        except SandboxError as e:
            from aegis.synthesize.generator import render_fallback

            fallback_src = render_fallback(goal, risks)
            audit.harness_code = fallback_src
            harness = load_harness(fallback_src, tool_callable=_tool_runtime)
            stage = StageRecord(
                name="synthesize_fallback",
                output={"reason": str(e), "fallback_source": fallback_src[:400]},
            )
            stage.mark_finished(ok=True, notes="generated harness failed to load; used template")
            audit.stages.append(stage)
            self._persist(audit)
            source = fallback_src

        # Repair budget: harness's own MAX_REPAIRS unless caller overrode it
        max_repairs = (
            self.max_repairs_override
            if self.max_repairs_override is not None
            else harness.max_repairs
        )

        value: Any = None
        for attempt in range(max_repairs + 1):
            # 4 — EXECUTE
            stage = StageRecord(name="execute" if attempt == 0 else f"execute_repair_{attempt}")
            try:
                value, tool_log, ti, to = await execute(goal, harness, self.provider, self.tools)
                stage.tokens_in, stage.tokens_out = ti, to
                stage.output = {"value": value, "n_tool_calls": len(tool_log)}
                audit.tool_calls.extend(tool_log)
                stage.mark_finished()
                audit.stages.append(stage)
                self._persist(audit)
            except Exception as e:
                stage.mark_finished(ok=False, notes=str(e))
                audit.stages.append(stage)
                self._persist(audit)
                if attempt >= max_repairs:
                    audit.succeeded = False
                    audit.finished_at = stage.finished_at
                    self._persist(audit)
                    return Result(value=None, harness_code=source, audit=audit, cached=cached)
                audit.repairs += 1
                continue

            # 5 — VERIFY
            v_stage = StageRecord(name="verify" if attempt == 0 else f"verify_repair_{attempt}")
            failures = verify_stage(value, harness, self.tools)
            v_stage.output = {"passed": not failures, "failures": failures}
            v_stage.mark_finished(ok=not failures)
            audit.stages.append(v_stage)
            self._persist(audit)

            if not failures:
                audit.succeeded = True
                audit.finished_at = v_stage.finished_at
                self._persist(audit)  # persist the terminal succeeded=True state
                return Result(value=value, harness_code=source, audit=audit, cached=cached)

            if attempt >= max_repairs:
                audit.succeeded = False
                audit.finished_at = v_stage.finished_at
                self._persist(audit)  # persist the terminal succeeded=False state
                return Result(value=value, harness_code=source, audit=audit, cached=cached)

            audit.repairs += 1
            # Use the harness's own repair-feedback message (custom or default)
            feedback = harness.repair_feedback(failures, value)
            goal = Goal(
                description=f"{goal.description}\n\n{feedback}",
                context=goal.context,
            )

        audit.succeeded = False
        self._persist(audit)
        return Result(value=value, harness_code=source, audit=audit, cached=cached)
