"""Cheap, dependency-free text similarity.

We avoid pulling in numpy/scipy for the default install — the cache works fine
with a character-trigram Jaccard similarity. Users who install
``aegis-harness[embeddings]`` get a real embedding-based implementation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def trigrams(text: str) -> set[str]:
    """Lowercase character-trigram set over alnum + space.

    We strip punctuation and collapse whitespace so paraphrases with the same
    content words still score highly.
    """
    norm = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if len(norm) < 3:
        return {norm}
    return {norm[i : i + 3] for i in range(len(norm) - 2)}


def similarity(a: str, b: str) -> float:
    """Jaccard similarity over character trigrams. Range [0, 1]."""
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def rank(query: str, corpus: Iterable[tuple[str, str]]) -> list[tuple[str, float]]:
    """Rank (id, text) pairs by similarity to query, descending."""
    scored = [(cid, similarity(query, text)) for cid, text in corpus]
    return sorted(scored, key=lambda x: x[1], reverse=True)
