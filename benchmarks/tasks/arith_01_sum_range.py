"""Arithmetic — sum the first 100 positive integers."""

GOAL = "Compute the sum of all positive integers from 1 to 100 inclusive. Return only the integer answer."
EXPECTED = 5050
RISK_ID = "arithmetic-drift"


def check(output) -> bool:
    if isinstance(output, dict):
        v = output.get("value", output.get("answer"))
    else:
        v = output
    try:
        return int(v) == EXPECTED
    except (TypeError, ValueError):
        return False
