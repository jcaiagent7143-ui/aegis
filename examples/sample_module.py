"""Toy module used by example 02. Intentionally has a too-large `process` fn."""

from __future__ import annotations


def process(records: list[dict[str, float]]) -> dict[str, float]:
    cleaned = []
    for r in records:
        if "value" not in r or r["value"] is None:
            continue
        if r["value"] < 0:
            continue
        cleaned.append(r)
    total = 0.0
    for r in cleaned:
        total += r["value"]
    mean = total / len(cleaned) if cleaned else 0.0
    variance = 0.0
    for r in cleaned:
        variance += (r["value"] - mean) ** 2
    variance = variance / len(cleaned) if cleaned else 0.0
    return {"n": len(cleaned), "total": total, "mean": mean, "variance": variance}
