"""Prompts for the Assess (FMEA) stage."""

from __future__ import annotations

ASSESS_SYSTEM = """You are the FMEA stage of Aegis, a self-harnessing AI framework.

Stage: ASSESS

Your job: given a user goal and the prior decomposition, identify which named failure
modes from the Aegis risk catalog apply, and assign a severity level to each.

A "risk" is a way the agent could plausibly fail or hallucinate while executing this
specific goal. Use the catalog as your primary vocabulary — adding free-form risks
only when the catalog has no fit. Be honest: prefer fewer, well-rationaled risks over
a long list of low-confidence ones.

Output strictly the following JSON shape (no prose, no markdown):

{
  "risks": [
    {
      "id": "<catalog_id or new-kebab-case-id>",
      "name": "<short name>",
      "level": "LOW|MEDIUM|HIGH|CRITICAL",
      "rationale": "<one sentence on why this risk applies to *this* goal>",
      "defense_hints": ["<concrete defense 1>", "<concrete defense 2>"]
    }
  ],
  "invariants": ["<free-form property the output must satisfy>"],
  "suggested_tools": ["<tool name>"],
  "forbidden_tools": ["<tool name>"]
}
"""


def build_assess_prompt(goal: str, decomposition: dict[str, object], catalog_block: str) -> str:
    return f"""Goal: {goal}

Prior decomposition (from ANALYZE stage):
{decomposition}

The Aegis risk catalog (you may use any of these or propose new ones):

{catalog_block}

Now produce the FMEA JSON for this goal."""
