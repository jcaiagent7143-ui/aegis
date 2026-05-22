"""Core abstractions: Goal, Result, AuditTrail, RiskProfile, and the Aegis facade."""

from aegis.core.aegis import Aegis
from aegis.core.goal import Goal
from aegis.core.result import AuditTrail, Result, StageRecord
from aegis.core.risk import Risk, RiskLevel, RiskProfile

__all__ = [
    "Aegis",
    "AuditTrail",
    "Goal",
    "Result",
    "Risk",
    "RiskLevel",
    "RiskProfile",
    "StageRecord",
]
