"""Risk catalog sanity tests."""

from aegis.assess.risk_catalog import CATALOG, keyword_filter, lookup
from aegis.core.risk import RiskLevel


def test_catalog_is_nonempty_and_unique():
    assert len(CATALOG) >= 30, "Risk catalog should have at least 30 entries"
    ids = [e.id for e in CATALOG]
    assert len(set(ids)) == len(ids), "Duplicate ids in catalog"


def test_catalog_entries_well_formed():
    for entry in CATALOG:
        assert entry.id and entry.name and entry.description
        assert isinstance(entry.typical_level, RiskLevel)
        # Either defenses or schema/verifier hint should be present for usefulness
        assert entry.defense_hints or entry.schema_hint or entry.verifier_hint


def test_lookup_by_id():
    e = lookup("citation-hallucination")
    assert e is not None
    assert e.typical_level == RiskLevel.HIGH


def test_keyword_filter_matches():
    hits = keyword_filter("Find the top 5 startups in YC W26 batch")
    ids = {e.id for e in hits}
    assert "citation-hallucination" in ids
    assert "ranking-ambiguity" in ids
