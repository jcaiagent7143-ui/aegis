"""Aegis — dynamic, on-the-fly generated harnesses for AI agents.

The agent designs its own guardrails before executing the task.

>>> import asyncio
>>> from aegis import Aegis
>>> async def main():
...     aegis = Aegis()
...     result = await aegis.run("What's 2 + 2?")
...     print(result.value)
>>> asyncio.run(main())  # doctest: +SKIP
"""

from aegis.core.aegis import Aegis
from aegis.core.goal import Goal
from aegis.core.result import AuditTrail, Result, StageRecord
from aegis.core.risk import Risk, RiskLevel, RiskProfile

__version__ = "0.5.4"

__all__ = [
    "Aegis",
    "AuditTrail",
    "Goal",
    "Result",
    "Risk",
    "RiskLevel",
    "RiskProfile",
    "StageRecord",
    "__version__",
]
