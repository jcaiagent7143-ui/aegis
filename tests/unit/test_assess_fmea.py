"""FMEA stage: ensures we always merge keyword-triggered risks."""

from __future__ import annotations

import json

import pytest

from aegis.assess.fmea import assess
from aegis.core.goal import Goal
from aegis.providers.mock import Mock


@pytest.mark.asyncio
async def test_keyword_hit_always_included():
    # Mock returns an FMEA with NO risks
    provider = Mock(
        responses=[
            json.dumps(
                {"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}
            )
        ]
    )
    goal = Goal(description="Find the top 5 startups in YC W26 batch")
    profile, _, _ = await assess(goal, {}, provider)

    ids = {r.id for r in profile.risks}
    # Keyword-merger should have backfilled at least these:
    assert "citation-hallucination" in ids
    assert "ranking-ambiguity" in ids


@pytest.mark.asyncio
async def test_explicit_risks_normalized():
    provider = Mock(
        responses=[
            json.dumps(
                {
                    "risks": [
                        {
                            "id": "arithmetic-drift",
                            "name": "Arithmetic drift",
                            "level": "high",
                            "rationale": "sum task",
                        }
                    ],
                    "invariants": ["value must be int"],
                    "suggested_tools": ["run_python_snippet"],
                    "forbidden_tools": [],
                }
            )
        ]
    )
    goal = Goal(description="Compute the sum of 1..100")
    profile, _, _ = await assess(goal, {}, provider)

    drift = next(r for r in profile.risks if r.id == "arithmetic-drift")
    assert drift.level.value == "HIGH"
    assert profile.invariants == ["value must be int"]
    assert "run_python_snippet" in profile.suggested_tools
