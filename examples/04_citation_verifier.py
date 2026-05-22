"""Example 04 — Deep dive on the citation-hallucination defense.

We run the same goal twice:

  1. With Aegis (full pipeline, with the synthesized citation verifier).
  2. Bypassing Aegis (direct provider call, no harness).

…then we compare the URLs in each output, fetching them to see how many
actually resolve. Aegis should win by a wide margin on the verifier metric.
"""

from __future__ import annotations

import asyncio
import re

import httpx

from aegis import Aegis
from aegis.providers import auto_provider
from aegis.providers.base import Message

GOAL = (
    "List 5 well-known academic papers on Mixture-of-Experts language models. "
    "For each, include the paper title and the arxiv URL."
)

URL_RE = re.compile(r"https?://[^\s\"'<>)]+")


async def fetch_ok(url: str) -> bool:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as c:
            r = await c.get(url)
            return r.status_code == 200
    except Exception:
        return False


async def main() -> None:
    aegis = Aegis()

    print("running Aegis pipeline …")
    aegis_result = await aegis.run(GOAL)
    aegis_text = str(aegis_result.value)
    aegis_urls = list(set(URL_RE.findall(aegis_text)))

    print("running bare provider call (no harness) …")
    provider = auto_provider()
    raw = await provider.complete([Message.user(GOAL)], temperature=0.2)
    bare_urls = list(set(URL_RE.findall(raw.text)))

    print("\nverifying URLs (HTTP GET) …")
    aegis_ok = sum(await asyncio.gather(*(fetch_ok(u) for u in aegis_urls)))
    bare_ok = sum(await asyncio.gather(*(fetch_ok(u) for u in bare_urls)))

    print(f"\n  aegis : {aegis_ok}/{len(aegis_urls)} URLs resolved")
    print(f"  bare  : {bare_ok}/{len(bare_urls)} URLs resolved")
    print("\n→ Aegis should produce a higher ratio because the synthesized")
    print("   verifier rejected any output containing a non-resolvable URL.")


if __name__ == "__main__":
    asyncio.run(main())
