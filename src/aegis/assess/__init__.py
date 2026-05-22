"""Stage 2 — Assess: Failure-Mode and Effects Analysis."""

from aegis.assess.fmea import assess
from aegis.assess.risk_catalog import CATALOG, CatalogEntry, lookup

__all__ = ["CATALOG", "CatalogEntry", "assess", "lookup"]
