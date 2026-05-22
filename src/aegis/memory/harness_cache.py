"""Harness cache — embed past goals, reuse the harnesses that worked."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from aegis.core.risk import RiskProfile
from aegis.memory.embeddings import rank


class CachedHarness(BaseModel):
    """A persisted harness keyed by its goal."""

    hash: str
    goal: str
    harness_code: str
    risks: RiskProfile
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    hits: int = 0


class HarnessCache:
    """Embedding-keyed cache of harnesses.

    Storage layout::

        <root>/
          index.json          # [{hash, goal}, ...]
          <hash>.json         # full CachedHarness
    """

    SIMILARITY_THRESHOLD = 0.45

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────────────

    def lookup(self, goal: str) -> CachedHarness | None:
        """Return the best-matching cached harness above the similarity threshold."""
        index = self._load_index()
        if not index:
            return None
        ranked = rank(goal, [(e["hash"], e["goal"]) for e in index])
        if not ranked:
            return None
        best_hash, best_score = ranked[0]
        if best_score < self.SIMILARITY_THRESHOLD:
            return None
        return self._load(best_hash)

    def put(self, goal: str, harness_code: str, risks: RiskProfile) -> CachedHarness:
        h = _stable_hash(goal)
        entry = CachedHarness(hash=h, goal=goal, harness_code=harness_code, risks=risks)
        self._save(entry)
        self._upsert_index(entry)
        return entry

    def list(self) -> list[CachedHarness]:
        return [self._load(e["hash"]) for e in self._load_index()]

    def get(self, h: str) -> CachedHarness | None:
        path = self.root / f"{h}.json"
        if not path.exists():
            return None
        return self._load(h)

    def clear(self) -> int:
        n = 0
        for p in self.root.glob("*.json"):
            p.unlink()
            n += 1
        return n

    def record_hit(self, h: str) -> None:
        entry = self._load(h)
        if entry is None:
            return
        entry.hits += 1
        self._save(entry)

    # ── internals ─────────────────────────────────────────────────────────

    def _index_path(self) -> Path:
        return self.root / "index.json"

    def _load_index(self) -> list[dict[str, str]]:
        p = self._index_path()
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            return []
        return [e for e in data if isinstance(e, dict) and "hash" in e and "goal" in e]

    def _upsert_index(self, entry: CachedHarness) -> None:
        idx = self._load_index()
        idx = [e for e in idx if e.get("hash") != entry.hash]
        idx.append({"hash": entry.hash, "goal": entry.goal})
        self._index_path().write_text(json.dumps(idx, indent=2))

    def _load(self, h: str) -> CachedHarness:
        return CachedHarness.model_validate_json((self.root / f"{h}.json").read_text())

    def _save(self, entry: CachedHarness) -> None:
        (self.root / f"{entry.hash}.json").write_text(entry.model_dump_json(indent=2))


def _stable_hash(s: str) -> str:
    return hashlib.sha256(s.strip().lower().encode("utf-8")).hexdigest()[:16]
