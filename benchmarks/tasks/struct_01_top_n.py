"""Output-shape — list of exactly N items (truncated-list risk)."""

GOAL = "List exactly 5 noble gases. Return the answer as JSON: {\"gases\": [...]}."
EXPECTED = 5
RISK_ID = "truncated-list"

NOBLE = {"helium", "neon", "argon", "krypton", "xenon", "radon", "oganesson"}


def check(output) -> bool:
    if isinstance(output, dict):
        items = output.get("gases", output.get("value", []))
    else:
        items = output
    if not isinstance(items, list) or len(items) != 5:
        return False
    return all(isinstance(x, str) and x.strip().lower() in NOBLE for x in items)
