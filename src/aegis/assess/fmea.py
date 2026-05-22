"""Stage 2 — FMEA: build a RiskProfile for the goal."""

from __future__ import annotations

from typing import Any

from aegis.assess.prompts import ASSESS_SYSTEM, build_assess_prompt
from aegis.assess.risk_catalog import (
    catalog_summary_for_prompt,
    keyword_filter,
    lookup,
)
from aegis.core.goal import Goal
from aegis.core.risk import Risk, RiskLevel, RiskProfile
from aegis.providers.base import Message, Provider
from aegis.utils.json_io import extract_json


async def assess(
    goal: Goal,
    decomposition: dict[str, Any],
    provider: Provider,
) -> tuple[RiskProfile, int, int]:
    """Run FMEA; returns (profile, tokens_in, tokens_out)."""
    catalog_block = catalog_summary_for_prompt()
    user = build_assess_prompt(goal.description, decomposition, catalog_block)
    response = await provider.complete(
        [Message.system(ASSESS_SYSTEM), Message.user(user)],
        temperature=0.1,
        max_tokens=2048,
        json_only=True,
    )

    data = extract_json(response.text) or {}
    profile = _to_profile(data, goal=goal)

    # Always merge keyword-filter hits so we don't miss obvious ones
    _merge_keyword_hits(profile, goal)

    return profile, response.tokens_in, response.tokens_out


def _to_profile(data: dict[str, Any], *, goal: Goal) -> RiskProfile:
    raw_risks = data.get("risks") or []
    risks: list[Risk] = []
    seen: set[str] = set()
    for r in raw_risks:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "").strip() or _slugify(str(r.get("name") or "unknown"))
        if rid in seen:
            continue
        seen.add(rid)
        level = _coerce_level(r.get("level"))
        name = str(r.get("name") or rid).strip()
        rationale = str(r.get("rationale") or "").strip()
        hints = list(r.get("defense_hints") or [])
        # Backfill defense hints from catalog if model didn't provide any
        if not hints:
            cat = lookup(rid)
            if cat:
                hints = list(cat.defense_hints)
        risks.append(Risk(id=rid, name=name, level=level, rationale=rationale, defense_hints=hints))

    return RiskProfile(
        risks=risks,
        invariants=[str(x) for x in (data.get("invariants") or [])],
        suggested_tools=[str(x) for x in (data.get("suggested_tools") or [])],
        forbidden_tools=[str(x) for x in (data.get("forbidden_tools") or [])],
        notes=f"FMEA for goal: {goal.description[:120]}",
    )


def _merge_keyword_hits(profile: RiskProfile, goal: Goal) -> None:
    """Ensure the most obvious keyword-triggered risks are present."""
    existing = {r.id for r in profile.risks}
    for entry in keyword_filter(goal.description):
        if entry.id in existing:
            continue
        profile.risks.append(
            Risk(
                id=entry.id,
                name=entry.name,
                level=entry.typical_level,
                rationale=f"Keyword-triggered: '{', '.join(entry.trigger_keywords)}' present in goal.",
                defense_hints=list(entry.defense_hints),
            )
        )


def _coerce_level(v: object) -> RiskLevel:
    if isinstance(v, RiskLevel):
        return v
    if isinstance(v, str):
        try:
            return RiskLevel(v.upper())
        except ValueError:
            pass
    return RiskLevel.MEDIUM


def _slugify(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " _-":
            out.append("-")
    return "".join(out).strip("-") or "unknown-risk"
