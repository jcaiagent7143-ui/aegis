"""Risk profile — the output of the FMEA (assess) stage."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """How dangerous a given failure mode is for the current goal."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def weight(self) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}[self.value]


class Risk(BaseModel):
    """A single identified failure mode."""

    id: str = Field(
        description="Stable identifier from the risk catalog, e.g. 'citation-hallucination'."
    )
    name: str = Field(description="Human-readable name.")
    level: RiskLevel
    rationale: str = Field(description="Why this risk applies to *this* goal.")
    defense_hints: list[str] = Field(
        default_factory=list,
        description="Concrete defenses to suggest to the synthesizer "
        "(e.g. 'add Pydantic regex for URLs', 'add post-hoc verifier').",
    )

    def __str__(self) -> str:
        return f"[{self.level.value:>8}] {self.id}: {self.rationale}"


class RiskProfile(BaseModel):
    """The full FMEA output for a goal."""

    risks: list[Risk] = Field(default_factory=list)
    invariants: list[str] = Field(
        default_factory=list,
        description="Free-form properties the output must satisfy.",
    )
    suggested_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def total_weight(self) -> int:
        return sum(r.level.weight for r in self.risks)

    @property
    def max_level(self) -> RiskLevel:
        if not self.risks:
            return RiskLevel.LOW
        return max(self.risks, key=lambda r: r.level.weight).level

    def summary(self) -> dict[str, Any]:
        return {
            "n_risks": len(self.risks),
            "max_level": self.max_level.value,
            "total_weight": self.total_weight,
            "by_level": {
                lvl.value: sum(1 for r in self.risks if r.level is lvl) for lvl in RiskLevel
            },
        }
