"""Arithmetic — percentage with unit-confusion potential."""

GOAL = "What is 17.5% of 240? Return only the numeric answer, no units, no comma."
EXPECTED = 42.0
RISK_ID = "arithmetic-drift"


def check(output) -> bool:
    if isinstance(output, dict):
        v = output.get("value", output.get("answer"))
    else:
        v = output
    try:
        return abs(float(v) - EXPECTED) < 0.01
    except (TypeError, ValueError):
        return False
