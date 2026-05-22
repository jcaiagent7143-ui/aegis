"""Tests for the v0.3 contract: the harness module carries the full runtime spec.

The LLM may emit any of: SYSTEM_PROMPT, MAX_STEPS, MAX_REPAIRS,
MAX_TOKENS_PER_TURN, TEMPERATURE, TOOL_OVERRIDES, repair_feedback.
The sandbox must extract them with sensible defaults + bounds, and the
executor + pipeline must honor whatever was emitted.
"""

from __future__ import annotations

import json

import pytest

from aegis import Aegis
from aegis.providers.mock import Mock
from aegis.synthesize.sandbox import DEFAULT_SYSTEM_PROMPT, load_harness

MINIMAL_HARNESS = """\
from pydantic import BaseModel

class Output(BaseModel):
    value: str = ""

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""

FULL_HARNESS = """\
from pydantic import BaseModel

SYSTEM_PROMPT = "You are a precision-obsessed financial analyst. Cite everything."
MAX_STEPS = 12
MAX_REPAIRS = 3
MAX_TOKENS_PER_TURN = 4000
TEMPERATURE = 0.1

TOOL_OVERRIDES = {
    "get_quote": "Call FIRST for any price question. Stale = wrong.",
}

class Output(BaseModel):
    value: str

ALLOWED_TOOLS: list[str] = ["get_quote"]

def verify(output: Output) -> list[str]:
    return []

def repair_feedback(failures, output):
    return f"FIX THESE: {failures}"
"""

OUT_OF_BOUNDS_HARNESS = """\
from pydantic import BaseModel

# These should all clamp to safe ranges
MAX_STEPS = 999
MAX_REPAIRS = -5
MAX_TOKENS_PER_TURN = 999999
TEMPERATURE = 7.5

class Output(BaseModel):
    value: str = ""

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""

INVALID_TYPES_HARNESS = """\
from pydantic import BaseModel

# Wrong types — should fall back to defaults silently
MAX_STEPS = "ten"
MAX_REPAIRS = 3.14
TEMPERATURE = "hot"
TOOL_OVERRIDES = ["not", "a", "dict"]
SYSTEM_PROMPT = 42

class Output(BaseModel):
    value: str = ""

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""


class TestMinimalContract:
    def test_minimal_harness_uses_defaults(self):
        """A harness with only the 3 required fields should use defaults for the rest."""
        h = load_harness(MINIMAL_HARNESS)
        assert h.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert h.max_steps == 8
        assert h.max_repairs == 1
        assert h.max_tokens_per_turn == 2048
        assert h.temperature == 0.0
        assert h.tool_overrides == {}
        assert h.repair_feedback_fn is None


class TestFullContract:
    def test_full_harness_overrides_every_default(self):
        h = load_harness(FULL_HARNESS)
        assert "precision-obsessed" in h.system_prompt
        assert h.max_steps == 12
        assert h.max_repairs == 3
        assert h.max_tokens_per_turn == 4000
        assert h.temperature == 0.1
        assert h.tool_overrides == {
            "get_quote": "Call FIRST for any price question. Stale = wrong."
        }
        assert h.repair_feedback_fn is not None

    def test_repair_feedback_uses_custom_function(self):
        h = load_harness(FULL_HARNESS)
        out = h.output_model.model_validate({"value": "x"})
        msg = h.repair_feedback(["bad URL", "bad date"], out)
        assert "FIX THESE" in msg
        assert "bad URL" in msg

    def test_repair_feedback_default_when_no_function(self):
        h = load_harness(MINIMAL_HARNESS)
        out = h.output_model.model_validate({"value": "x"})
        msg = h.repair_feedback(["failed X"], out)
        assert "failed X" in msg
        assert "Address" in msg or "fix" in msg.lower() or "re-fetch" in msg.lower()


class TestBoundsAndCoercion:
    def test_out_of_bounds_values_clamped(self):
        h = load_harness(OUT_OF_BOUNDS_HARNESS)
        assert h.max_steps == 50  # clamped to upper bound
        assert h.max_repairs == 0  # clamped to lower bound
        assert h.max_tokens_per_turn == 16384  # clamped
        assert h.temperature == 2.0  # clamped

    def test_wrong_types_fall_back_to_defaults(self):
        h = load_harness(INVALID_TYPES_HARNESS)
        # Every wrong-typed field should silently use the default
        assert h.max_steps == 8
        assert h.max_repairs == 1
        assert h.temperature == 0.0
        assert h.tool_overrides == {}
        assert h.system_prompt == DEFAULT_SYSTEM_PROMPT


class TestPipelineHonorsHarnessRepairs:
    @pytest.mark.asyncio
    async def test_harness_max_repairs_used_when_no_override(self, tmp_path):
        """The pipeline should use the harness's MAX_REPAIRS, not a hardcoded value."""
        # Harness says MAX_REPAIRS = 0 → only one execute attempt, no repair on failure
        harness_with_zero_repairs = """\
from pydantic import BaseModel

MAX_REPAIRS = 0

class Output(BaseModel):
    value: str

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return ["always fail"]
"""
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
            json.dumps(
                {"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}
            ),
            # synthesize
            harness_with_zero_repairs,
            # execute (one attempt only — no repair because MAX_REPAIRS=0)
            json.dumps({"value": "answer"}),
        ]
        provider = Mock(responses=scripted)
        aegis = Aegis(provider=provider, cache_dir=tmp_path, enable_cache=False)
        result = await aegis.run("test")
        assert not result.audit.succeeded
        # Should NOT have a repair attempt
        assert result.audit.repairs == 0
        # Should have exactly ONE execute stage and ONE verify stage
        execute_stages = [s for s in result.audit.stages if s.name.startswith("execute")]
        assert len(execute_stages) == 1

    @pytest.mark.asyncio
    async def test_aegis_override_beats_harness(self, tmp_path):
        """Aegis(max_repairs=N) should override the harness's value."""
        harness_with_many_repairs = """\
from pydantic import BaseModel

MAX_REPAIRS = 5  # harness wants 5 retries

class Output(BaseModel):
    value: str

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return ["always fail"]
"""
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
            json.dumps(
                {"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}
            ),
            harness_with_many_repairs,
            json.dumps({"value": "v1"}),
            json.dumps({"value": "v2"}),  # repair attempt
        ]
        provider = Mock(responses=scripted)
        # Override: cap at 1 repair regardless of harness
        aegis = Aegis(provider=provider, cache_dir=tmp_path, enable_cache=False, max_repairs=1)
        result = await aegis.run("test")
        assert not result.audit.succeeded
        # Exactly one repair, not five
        assert result.audit.repairs == 1
