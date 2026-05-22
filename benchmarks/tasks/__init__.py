"""Benchmark tasks — each module defines: goal, expected, check(output)."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any, NamedTuple


class Task(NamedTuple):
    name: str
    goal: str
    expected: Any
    check: Callable[[Any], bool]
    risk_id: str


def discover() -> list[Task]:
    """Return every task module in this package as a Task."""
    out: list[Task] = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "tasks":
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        out.append(
            Task(
                name=info.name,
                goal=mod.GOAL,
                expected=getattr(mod, "EXPECTED", None),
                check=mod.check,
                risk_id=getattr(mod, "RISK_ID", "schema-drift"),
            )
        )
    return sorted(out, key=lambda t: t.name)
