"""Result + AuditTrail — what every Aegis run produces."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis.core.risk import RiskProfile


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class StageRecord(BaseModel):
    """A record of a single pipeline stage execution."""

    name: str
    started_at: str = Field(default_factory=_utc_now)
    finished_at: str | None = None
    ok: bool = True
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    notes: str = ""
    output: dict[str, Any] = Field(default_factory=dict)

    def mark_finished(self, *, ok: bool = True, notes: str = "") -> None:
        self.finished_at = _utc_now()
        self.ok = ok
        self.notes = notes
        try:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.finished_at)
            self.duration_ms = (end - start).total_seconds() * 1000.0
        except ValueError:
            self.duration_ms = 0.0


class AuditTrail(BaseModel):
    """Complete record of an Aegis run — every stage, every tool call, every retry."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    goal: str
    provider: str
    started_at: str = Field(default_factory=_utc_now)
    finished_at: str | None = None
    stages: list[StageRecord] = Field(default_factory=list)
    risks: RiskProfile = Field(default_factory=RiskProfile)
    harness_code: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    repairs: int = 0
    succeeded: bool = False

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens_in + s.tokens_out for s in self.stages)

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.stages)

    def stage(self, name: str) -> StageRecord | None:
        for s in self.stages:
            if s.name == name:
                return s
        return None

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path) -> AuditTrail:
        return cls.model_validate_json(Path(path).read_text())


class Result(BaseModel):
    """What the user gets back from `aegis.run(...)`."""

    value: Any = Field(description="The verified, validated answer.")
    harness_code: str = Field(description="The Python source of the synthesized harness.")
    audit: AuditTrail
    cached: bool = Field(default=False, description="Whether the harness was reused from cache.")

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            {
                "value": self.value if _json_safe(self.value) else str(self.value),
                "cached": self.cached,
                "audit_summary": {
                    "run_id": self.audit.run_id,
                    "provider": self.audit.provider,
                    "succeeded": self.audit.succeeded,
                    "total_tokens": self.audit.total_tokens,
                    "total_duration_ms": self.audit.total_duration_ms,
                    "risks": self.audit.risks.summary(),
                    "repairs": self.audit.repairs,
                    "tool_calls": len(self.audit.tool_calls),
                },
            },
            indent=indent,
        )


def _json_safe(v: Any) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False
