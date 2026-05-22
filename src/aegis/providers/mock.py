"""Mock provider — produces deterministic, hand-crafted responses.

Used for:
  * Tests (so unit tests don't need an API key)
  * The CLI fallback when no real provider is configured (so `pip install
    self-harness && aegis run "..."` works out of the box for exploration)
  * Replay & demos
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from aegis.providers.base import Completion, Message, Tool


class Mock:
    """A deterministic, scripted provider.

    Two modes:

    1. **Pattern mode** (default): the mock inspects the last user message and
       returns a canned response for the *stage* it can detect from the prompt
       header. Good enough to run the full pipeline end-to-end with no API key.

    2. **Scripted mode**: pass ``responses=[...]`` to play back exact strings
       in order. Used by tests.
    """

    name = "mock"

    def __init__(
        self,
        model: str = "mock-1",
        *,
        responses: list[str] | None = None,
        handler: Callable[[list[Message]], str] | None = None,
    ) -> None:
        self.model = model
        self._scripted = list(responses) if responses else None
        self._handler = handler

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        if self._handler:
            text = self._handler(messages)
        elif self._scripted:
            text = self._scripted.pop(0) if self._scripted else "{}"
        else:
            text = _canned_response(messages)

        return Completion(
            text=text,
            tokens_in=sum(len(m.content) for m in messages) // 4,
            tokens_out=len(text) // 4,
            finish_reason="stop",
        )


def _canned_response(messages: list[Message]) -> str:
    """Best-effort: detect which stage is asking and produce a plausible reply."""
    last = messages[-1].content if messages else ""
    sys = " ".join(m.content for m in messages if m.role == "system")
    blob = (sys + "\n" + last).lower()
    goal = _extract_goal(last)

    if "stage: analyze" in blob or "decompose" in blob:
        return json.dumps(
            {
                "summary": f"Goal: {goal[:120]}",
                "deliverable": "Concise, verifiable answer",
                "output_schema_hint": "JSON object with the answer plus a short rationale",
                "needed_tools": _guess_tools(goal),
                "open_questions": [],
            }
        )

    if "stage: assess" in blob or "failure mode" in blob or "fmea" in blob:
        return json.dumps(
            {
                "risks": _guess_risks(goal),
                "invariants": ["output must be JSON-parseable", "no fabricated citations"],
                "suggested_tools": _guess_tools(goal),
                "forbidden_tools": _guess_forbidden(goal),
            }
        )

    if "stage: synthesize" in blob or "generate harness" in blob:
        return _STUB_HARNESS

    if "stage: execute" in blob or "agent loop" in blob:
        return json.dumps({"value": f"[mock answer to: {goal[:80]}]", "rationale": "stub"})

    if "stage: verify" in blob or "post-hoc check" in blob:
        return json.dumps({"passed": True, "failures": []})

    # Generic JSON fallback
    return json.dumps({"value": f"[mock] {goal[:120]}"})


def _extract_goal(text: str) -> str:
    m = re.search(r"goal:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    return (m.group(1) if m else text).strip()


def _guess_tools(goal: str) -> list[str]:
    g = goal.lower()
    if any(k in g for k in ("search", "find", "research", "look up")):
        return ["web_search", "fetch_url"]
    if any(k in g for k in ("file", ".py", "code", "refactor")):
        return ["read_file"]
    if any(k in g for k in ("csv", "data", "compute", "sum")):
        return ["read_file", "run_python"]
    return []


def _guess_forbidden(goal: str) -> list[str]:
    g = goal.lower()
    if any(k in g for k in ("search", "find", "research")):
        return ["run_python"]
    return []


def _guess_risks(goal: str) -> list[dict[str, Any]]:
    g = goal.lower()
    out: list[dict[str, Any]] = []
    if any(k in g for k in ("find", "research", "list", "citation")):
        out.append(
            {
                "id": "citation-hallucination",
                "name": "Citation hallucination",
                "level": "HIGH",
                "rationale": "Open-ended retrieval goal — model may invent sources.",
                "defense_hints": ["regex-validate URLs", "post-hoc fetch verifier"],
            }
        )
    if any(k in g for k in ("compute", "sum", "csv", "average", "count")):
        out.append(
            {
                "id": "arithmetic-drift",
                "name": "Arithmetic drift",
                "level": "HIGH",
                "rationale": "Numeric task — model often miscalculates.",
                "defense_hints": ["recompute from raw data", "bound numeric fields"],
            }
        )
    if any(k in g for k in ("code", "refactor", "edit", ".py")):
        out.append(
            {
                "id": "untested-edit",
                "name": "Untested code edit",
                "level": "MEDIUM",
                "rationale": "Edits may break existing behavior without verification.",
                "defense_hints": ["run existing tests", "AST diff before/after"],
            }
        )
    if not out:
        out.append(
            {
                "id": "schema-drift",
                "name": "Output schema drift",
                "level": "LOW",
                "rationale": "Generic risk — output may not match expected shape.",
                "defense_hints": ["validate with Pydantic"],
            }
        )
    return out


_STUB_HARNESS = """\
# AUTO-GENERATED HARNESS (mock)
from pydantic import BaseModel, Field

class Output(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(max_length=500)

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""
