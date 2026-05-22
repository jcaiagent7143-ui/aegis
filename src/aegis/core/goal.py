"""The Goal abstraction — what the user wants the agent to do."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class Goal(BaseModel):
    """A task the user wants Aegis to perform.

    A Goal is intentionally minimal — just the natural-language description
    plus optional context. Aegis derives everything else (output shape,
    tools needed, failure modes) by reasoning about the description.
    """

    description: str = Field(min_length=1, description="What the user wants accomplished.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra context (files, prior state, constraints).",
    )
    tool_hints: list[str] = Field(
        default_factory=list,
        description="Optional hints about which tools the agent may need.",
    )
    deadline_s: float | None = Field(
        default=None, ge=0, description="Soft wall-clock deadline in seconds."
    )
    id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:12]}")

    def __str__(self) -> str:
        return self.description
