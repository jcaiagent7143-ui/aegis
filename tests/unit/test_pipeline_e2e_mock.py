"""End-to-end pipeline test using the Mock provider.

This is the most important test: a full Aegis run from goal to verified
output, using zero network and no API keys. If this breaks, the project
is broken from the user's perspective.
"""

from __future__ import annotations

import json

import pytest

from aegis import Aegis
from aegis.providers.mock import Mock

GOOD_HARNESS_SRC = """\
from pydantic import BaseModel, Field

class Output(BaseModel):
    value: str = Field(min_length=1)
    rationale: str = ""

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""


@pytest.mark.asyncio
async def test_pipeline_e2e_with_mock(tmp_path):
    scripted = [
        # analyze
        json.dumps(
            {
                "summary": "test goal",
                "deliverable": "a string answer",
                "output_schema_hint": "JSON {value, rationale}",
                "needed_tools": [],
                "open_questions": [],
            }
        ),
        # assess
        json.dumps(
            {
                "risks": [
                    {
                        "id": "schema-drift",
                        "name": "schema drift",
                        "level": "LOW",
                        "rationale": "tiny",
                    }
                ],
                "invariants": [],
                "suggested_tools": [],
                "forbidden_tools": [],
            }
        ),
        # synthesize
        GOOD_HARNESS_SRC,
        # execute
        json.dumps({"value": "42", "rationale": "computed"}),
        # verify (not invoked by provider — `verify(output)` is local Python)
    ]
    provider = Mock(responses=scripted)
    aegis = Aegis(provider=provider, cache_dir=tmp_path, enable_cache=False)
    result = await aegis.run("What's the answer?")

    assert result.audit.succeeded
    assert result.value["value"] == "42"
    assert "Output" in result.harness_code
    # All 5 stages should have produced records
    names = [s.name for s in result.audit.stages]
    assert "analyze" in names
    assert "assess" in names
    assert "synthesize" in names
    assert "execute" in names
    assert "verify" in names


@pytest.mark.asyncio
async def test_cache_hit_skips_synthesis(tmp_path):
    scripted_first = [
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
        GOOD_HARNESS_SRC,
        json.dumps({"value": "v1", "rationale": ""}),
    ]
    # Second run: only execute is invoked (cache hit skips 1-3)
    scripted_second = [json.dumps({"value": "v2", "rationale": ""})]

    p1 = Mock(responses=list(scripted_first))
    a1 = Aegis(provider=p1, cache_dir=tmp_path)
    r1 = await a1.run("repeatable goal")
    assert not r1.cached

    p2 = Mock(responses=list(scripted_second))
    a2 = Aegis(provider=p2, cache_dir=tmp_path)
    r2 = await a2.run("repeatable goal")
    assert r2.cached
    assert r2.value["value"] == "v2"


FAILING_HARNESS_SRC = """\
from pydantic import BaseModel, Field

class Output(BaseModel):
    value: str = Field(min_length=1)
    rationale: str = ""

ALLOWED_TOOLS: list[str] = []
MAX_REPAIRS = 0  # no retries — keep the test fast and deterministic

def verify(output: Output) -> list[str]:
    # Always fails so the pipeline reports succeeded=False, exactly the
    # signal the cache must use to decide NOT to persist this harness.
    return ["intentional failure for cache-poisoning regression test"]
"""


@pytest.mark.asyncio
async def test_failed_run_does_not_poison_cache(tmp_path):
    """Regression for the v0.5.3 e2e bug: a failed first run cached its
    harness, and the next run for the same goal short-circuited to the
    broken harness instead of trying fresh synthesis.
    """
    scripted_failing = [
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
        FAILING_HARNESS_SRC,
        json.dumps({"value": "anything", "rationale": ""}),
    ]
    p1 = Mock(responses=list(scripted_failing))
    a1 = Aegis(provider=p1, cache_dir=tmp_path)
    r1 = await a1.run("poisoning probe")
    assert not r1.audit.succeeded, "verifier always fails => succeeded must be False"

    # Now a fresh run for the same goal must NOT find a cache entry.
    # If the cache was poisoned (the v0.5.3 bug), r2.cached would be True
    # and the broken FAILING_HARNESS_SRC would be replayed.
    p2 = Mock(
        responses=[
            json.dumps(
                {
                    "summary": "g",
                    "deliverable": "d",
                    "output_schema_hint": "x",
                    "needed_tools": [],
                    "open_questions": [],
                }
            ),
            json.dumps(
                {"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}
            ),
            GOOD_HARNESS_SRC,
            json.dumps({"value": "ok", "rationale": ""}),
        ]
    )
    a2 = Aegis(provider=p2, cache_dir=tmp_path)
    r2 = await a2.run("poisoning probe")
    assert not r2.cached, "failed run should not have populated the cache"
    assert r2.audit.succeeded
    assert r2.value["value"] == "ok"


@pytest.mark.asyncio
async def test_auto_fallback_mock_skips_cache(tmp_path):
    """A Mock instance tagged as auto-fallback (because env said the user
    wanted a real provider but the extra was missing) must not write to
    the cache — otherwise its `[mock] …` placeholder text would be
    silently replayed on subsequent real-provider sessions.

    This mirrors the v0.5.3 e2e bug where TEST 1 short-circuited from a
    poisoned cache populated by an earlier missing-extra Mock run.
    """
    from aegis.providers.mock import Mock as MockProvider

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
        GOOD_HARNESS_SRC,
        json.dumps({"value": "ok", "rationale": ""}),
    ]
    fallback = MockProvider(responses=list(scripted))
    fallback._is_auto_fallback = True  # type: ignore[attr-defined]
    a1 = Aegis(provider=fallback, cache_dir=tmp_path)
    r1 = await a1.run("auto fallback probe")
    assert r1.audit.succeeded

    # Now a real follow-up: cache must be empty so we don't replay the
    # auto-fallback Mock's harness.
    from aegis.memory.harness_cache import HarnessCache

    cache = HarnessCache(tmp_path / "harnesses")
    assert cache.list_all() == []
