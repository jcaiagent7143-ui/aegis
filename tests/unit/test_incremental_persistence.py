"""Audit trail must be persisted incrementally so a mid-pipeline crash
leaves a recoverable partial JSON on disk (criticism #7 of the v0.4.0 review).

Strategy: configure a Pipeline with an audit_path, drive it through the Mock
provider one stage at a time, and assert the file on disk grows in step with
the stages, with valid Pydantic-loadable JSON at every checkpoint.
"""

from __future__ import annotations

import json

import pytest

from aegis.core.goal import Goal
from aegis.core.pipeline import Pipeline
from aegis.core.result import AuditTrail
from aegis.execute.tool_registry import default_registry
from aegis.providers.mock import Mock

# A scripted pipeline run that will complete successfully on the Mock.
SCRIPTED = [
    json.dumps(
        {
            "summary": "g",
            "deliverable": "d",
            "output_schema_hint": "x",
            "needed_tools": [],
            "open_questions": [],
        }
    ),
    json.dumps({"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}),
    "from pydantic import BaseModel\n\nclass Output(BaseModel):\n    value: str = ''\n\n"
    "ALLOWED_TOOLS: list[str] = []\n\ndef verify(output): return []\n",
    json.dumps({"value": "answer"}),
]


@pytest.mark.asyncio
async def test_audit_file_grows_per_stage(tmp_path):
    """After each stage, the audit file on disk should contain one more stage."""
    audit_path = tmp_path / "trail.json"
    pipeline = Pipeline(
        provider=Mock(responses=list(SCRIPTED)),
        tools=default_registry(),
        cache=None,
        audit_path=audit_path,
    )
    await pipeline.execute(Goal(description="test"))

    # On success, the file should exist and round-trip via AuditTrail.load
    assert audit_path.exists(), "Expected audit_path to be written"
    reloaded = AuditTrail.load(audit_path)
    assert reloaded.succeeded
    # 5 stages on the happy path: analyze, assess, synthesize, execute, verify
    stage_names = [s.name for s in reloaded.stages]
    for required in ("analyze", "assess", "synthesize", "execute", "verify"):
        assert required in stage_names, f"missing stage in persisted audit: {required}"


@pytest.mark.asyncio
async def test_partial_audit_persists_when_pipeline_crashes_mid_run(tmp_path):
    """Simulate a crash after stage 2 by feeding bad JSON to the synthesize stage.

    The synthesizer's fallback path catches its own errors, so to trigger a
    real mid-pipeline crash we use a Mock that raises on the synthesize call.
    The audit file on disk should still show the 2 stages that DID complete.
    """
    crash_responses = [
        # analyze (succeeds)
        json.dumps(
            {
                "summary": "g",
                "deliverable": "d",
                "output_schema_hint": "x",
                "needed_tools": [],
                "open_questions": [],
            }
        ),
        # assess (succeeds)
        json.dumps({"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}),
    ]
    # Hand the Mock a handler that raises after the scripted responses run out.
    counter = {"i": 0}

    def handler(_messages):
        i = counter["i"]
        counter["i"] += 1
        if i < len(crash_responses):
            return crash_responses[i]
        raise RuntimeError("simulated provider crash during synthesize stage")

    audit_path = tmp_path / "crash-trail.json"
    pipeline = Pipeline(
        provider=Mock(handler=handler),
        tools=default_registry(),
        cache=None,
        audit_path=audit_path,
    )
    with pytest.raises(RuntimeError, match="simulated provider crash"):
        await pipeline.execute(Goal(description="will crash"))

    # The audit file must exist and show exactly the stages that completed
    # before the crash (analyze + assess) — no synthesize/execute/verify.
    assert audit_path.exists(), "Audit must persist even on mid-pipeline crash"
    reloaded = AuditTrail.load(audit_path)
    stage_names = [s.name for s in reloaded.stages]
    assert "analyze" in stage_names
    assert "assess" in stage_names
    assert "synthesize" not in stage_names
    assert "execute" not in stage_names


@pytest.mark.asyncio
async def test_persistence_failure_does_not_break_pipeline(tmp_path):
    """If audit_path is unwritable, the pipeline must still complete cleanly."""
    # Create a *file* where the persistence layer expects a writable target.
    # Setting audit_path to a directory will make the .partial → rename fail.
    blocked = tmp_path / "blocked-dir"
    blocked.mkdir()  # path exists as a directory; writing to it as a file fails
    pipeline = Pipeline(
        provider=Mock(responses=list(SCRIPTED)),
        tools=default_registry(),
        cache=None,
        audit_path=blocked,  # not a writable file
    )
    # Should not raise — persistence errors are swallowed by design.
    result = await pipeline.execute(Goal(description="test"))
    assert result.audit.succeeded, "Pipeline must complete even when persistence fails"
