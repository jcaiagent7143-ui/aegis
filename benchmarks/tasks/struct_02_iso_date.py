"""Format — return a strict ISO-8601 date (locale-confusion risk)."""

import re

GOAL = "What is the date 100 days after 2024-01-01? Return the answer as ISO 8601 (YYYY-MM-DD) only."
EXPECTED = "2024-04-10"
RISK_ID = "locale-confusion"

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check(output) -> bool:
    if isinstance(output, dict):
        v = output.get("value", output.get("date", ""))
    else:
        v = output
    v = str(v).strip()
    return ISO_RE.match(v) is not None and v == EXPECTED
