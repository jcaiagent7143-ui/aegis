"""Stage 1 — Analyze."""

from __future__ import annotations

from typing import Any

from aegis.analyze.prompts import ANALYZE_SYSTEM, build_analyze_prompt
from aegis.core.goal import Goal
from aegis.providers.base import Message, Provider
from aegis.utils.json_io import extract_json


async def analyze(goal: Goal, provider: Provider) -> tuple[dict[str, Any], int, int]:
    """Decompose the goal into a structured prior for downstream stages."""
    user = build_analyze_prompt(goal.description, goal.context)
    response = await provider.complete(
        [Message.system(ANALYZE_SYSTEM), Message.user(user)],
        temperature=0.1,
        max_tokens=1024,
        json_only=True,
    )
    data = extract_json(response.text) or {}
    return _normalize(data, goal), response.tokens_in, response.tokens_out


def _normalize(data: dict[str, Any], goal: Goal) -> dict[str, Any]:
    return {
        "summary": str(data.get("summary") or goal.description),
        "deliverable": str(data.get("deliverable") or "concise answer"),
        "output_schema_hint": str(
            data.get("output_schema_hint") or "a JSON object with a `value` field"
        ),
        "needed_tools": [str(x) for x in (data.get("needed_tools") or [])],
        "open_questions": [str(x) for x in (data.get("open_questions") or [])],
    }
