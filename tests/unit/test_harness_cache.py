"""Cache round-trip and similarity tests."""

from __future__ import annotations

from aegis.core.risk import Risk, RiskLevel, RiskProfile
from aegis.memory.harness_cache import HarnessCache


def _profile() -> RiskProfile:
    return RiskProfile(
        risks=[Risk(id="x", name="x", level=RiskLevel.LOW, rationale="...", defense_hints=[])]
    )


def test_put_and_lookup_exact(tmp_path):
    cache = HarnessCache(tmp_path / "h")
    cache.put("Find the top 5 startups in YC W26", "# harness", _profile())
    hit = cache.lookup("Find the top 5 startups in YC W26")
    assert hit is not None
    assert hit.harness_code == "# harness"


def test_lookup_similar_above_threshold(tmp_path):
    cache = HarnessCache(tmp_path / "h")
    cache.put("Find top 5 startups in YC W26 batch", "# h1", _profile())
    hit = cache.lookup("find the top 5 startups in YC's W26 batch please")
    assert hit is not None


def test_lookup_dissimilar_returns_none(tmp_path):
    cache = HarnessCache(tmp_path / "h")
    cache.put("Sum the numbers in sales.csv", "# h1", _profile())
    hit = cache.lookup("Quote me a Shakespeare sonnet")
    assert hit is None


def test_record_hit_increments(tmp_path):
    cache = HarnessCache(tmp_path / "h")
    entry = cache.put("g", "h", _profile())
    cache.record_hit(entry.hash)
    cache.record_hit(entry.hash)
    assert cache.get(entry.hash).hits == 2


def test_list_and_clear(tmp_path):
    cache = HarnessCache(tmp_path / "h")
    cache.put("a", "ha", _profile())
    cache.put("b", "hb", _profile())
    assert len(cache.list()) == 2
    assert cache.clear() >= 2
    assert cache.list() == []
