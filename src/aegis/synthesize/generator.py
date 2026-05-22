"""Stage 3 — Synthesize: produce the runtime harness Python source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aegis.core.goal import Goal
from aegis.core.risk import RiskProfile
from aegis.providers.base import Message, Provider
from aegis.synthesize.prompts import SYNTHESIZE_SYSTEM, build_synthesize_prompt
from aegis.synthesize.sandbox import SandboxError, load_harness, validate_source

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)


async def synthesize(
    goal: Goal,
    decomposition: dict[str, Any],
    risks: RiskProfile,
    tools_catalog: str,
    provider: Provider,
    *,
    max_attempts: int = 2,
) -> tuple[str, int, int]:
    """Generate a sandbox-valid harness module source. Returns (source, tokens_in, tokens_out)."""
    risks_block = (
        "\n\n".join(
            f"- {r.id} [{r.level.value}]: {r.rationale}\n  defenses: {'; '.join(r.defense_hints) or '(none)'}"
            for r in risks.risks
        )
        or "(no risks identified — use a minimal Pydantic-only harness)"
    )

    user = build_synthesize_prompt(goal.description, decomposition, risks_block, tools_catalog)

    tokens_in = tokens_out = 0
    last_error = ""
    for _attempt in range(max_attempts):
        messages = [Message.system(SYNTHESIZE_SYSTEM), Message.user(user)]
        if last_error:
            messages.append(
                Message.user(
                    f"Your previous attempt failed sandbox load: {last_error}\n\n"
                    "Emit a corrected module. Common fixes:\n"
                    "  * Pydantic Field names must NOT start with underscore "
                    "(use `caveats` not `_caveats`).\n"
                    "  * `Output` must inherit from `pydantic.BaseModel`.\n"
                    "  * `ALLOWED_TOOLS` must be `list[str]` of tool names from "
                    "the provided catalog.\n"
                    "  * `verify(output)` must return `list[str]`."
                )
            )
        response = await provider.complete(messages, temperature=0.1, max_tokens=3000)
        tokens_in += response.tokens_in
        tokens_out += response.tokens_out

        candidate = _strip_fences(response.text)
        try:
            # Two-phase validation: AST first (cheap, catches forbidden constructs)
            validate_source(candidate)
            # Then try a full load — catches pydantic schema errors, missing
            # interface names, runtime errors during class construction, etc.
            load_harness(candidate, tool_callable=None)
            return candidate, tokens_in, tokens_out
        except SandboxError as e:
            last_error = str(e)
            continue

    # All attempts failed — fall back to the deterministic template
    fallback = render_fallback(goal, risks)
    return fallback, tokens_in, tokens_out


def render_fallback(goal: Goal, risks: RiskProfile) -> str:
    """Render a guaranteed-valid harness from the local Jinja template.

    Sizes ``MAX_STEPS`` and ``MAX_REPAIRS`` to the risk profile: heavier risk
    profiles get more steps (to gather more evidence) and more repairs (to
    iterate on verifier failures).
    """
    tmpl = _env.get_template("harness.j2")
    risk_ids = {r.id for r in risks.risks}
    weight = risks.total_weight
    # Heuristic budgets — match how a careful engineer would scale them
    max_steps = 6 if weight <= 4 else 10 if weight <= 10 else 14
    max_repairs = 1 if weight <= 4 else 2
    return tmpl.render(
        goal=goal.description,
        risks=[{"level": r.level.value, "id": r.id, "rationale": r.rationale} for r in risks.risks],
        allowed_tools=risks.suggested_tools or [],
        has_url_risk="citation-hallucination" in risk_ids,
        has_arithmetic_risk="arithmetic-drift" in risk_ids,
        needs_criterion="ranking-ambiguity" in risk_ids,
        needs_confidence="overconfident-uncertainty" in risk_ids,
        max_steps=max_steps,
        max_repairs=max_repairs,
    )


def _strip_fences(text: str) -> str:
    """Strip ```python fences if the model added them anyway."""
    t = text.strip()
    m = re.match(r"^```(?:python|py)?\s*\n(.*?)\n```\s*$", t, re.DOTALL)
    if m:
        return m.group(1)
    return t
