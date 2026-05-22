"""Counting — count exact words in a fixed string (off-by-one risk)."""

TEXT = "the quick brown fox jumps over the lazy dog"
GOAL = f'How many words are in this sentence: "{TEXT}"? Return only the integer.'
EXPECTED = 9
RISK_ID = "off-by-one"


def check(output) -> bool:
    v = output.get("value", output.get("answer")) if isinstance(output, dict) else output
    try:
        return int(v) == EXPECTED
    except (TypeError, ValueError):
        return False
