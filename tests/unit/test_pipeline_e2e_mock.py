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
