"""Regression tests for the bugs found by the financial-agent live test.

These tests use the Mock provider with scripted responses to simulate
real-LLM failure modes:

  * The model emits a Pydantic class with a leading-underscore field name.
  * The model emits source that parses but raises during `class` evaluation.
  * The model emits source missing `Output` or `verify`.

In all cases the synthesizer's retry loop should attempt a corrected
generation, and if that still fails, the pipeline should fall back to the
deterministic template rather than crashing.
"""

from __future__ import annotations

import json

import pytest

from aegis import Aegis
from aegis.providers.mock import Mock

# Source emitted by a real LLM (gpt-5.4-nano) that AST-validates but fails to load
BAD_PYDANTIC = """\
from pydantic import BaseModel, Field

class Output(BaseModel):
    value: str
    _caveat_keywords: list[str] = Field(default_factory=list)

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""

GOOD_HARNESS = """\
from pydantic import BaseModel

class Output(BaseModel):
    value: str = ""

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""


@pytest.mark.asyncio
async def test_synthesize_retries_on_pydantic_error(tmp_path):
    """When attempt 1 emits bad pydantic, attempt 2 fixes it — pipeline succeeds."""
    scripted = [
        # analyze
        json.dumps(
            {
                "summary": "g",
                "deliverable": "d",
                "output_schema_hint": "x",
                "needed_tools": [],
                "open_questions": [],
            }
        ),
        # assess
        json.dumps({"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}),
        # synthesize attempt 1: bad pydantic
        BAD_PYDANTIC,
        # synthesize attempt 2: good harness
        GOOD_HARNESS,
        # execute
        json.dumps({"value": "answer"}),
    ]
    provider = Mock(responses=scripted)
    aegis = Aegis(provider=provider, cache_dir=tmp_path, enable_cache=False)
    result = await aegis.run("test goal")

    assert result.audit.succeeded
    # The good harness made it through after the retry
    assert "_caveat" not in result.harness_code


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_both_attempts_fail(tmp_path):
    """If the synthesizer never produces a loadable harness, fall back to template."""
    scripted = [
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
        BAD_PYDANTIC,  # attempt 1 fails
        BAD_PYDANTIC,  # attempt 2 fails too
        # execute against the template fallback
        json.dumps({"value": "answer", "rationale": "from fallback template"}),
    ]
    provider = Mock(responses=scripted)
    aegis = Aegis(provider=provider, cache_dir=tmp_path, enable_cache=False)
    result = await aegis.run("test goal")

    # Pipeline didn't crash. The template's Output schema is used.
    assert result.audit.succeeded
    # The harness in the audit is the deterministic template, not BAD_PYDANTIC
    assert (
        "AUTO-GENERATED HARNESS (fallback template)" in result.harness_code
        or "fallback" in result.harness_code.lower()
    )
