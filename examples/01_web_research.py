"""Example 01 — Web research with a synthesized citation verifier.

Run with::

    python examples/01_web_research.py

The goal is open-ended, so Aegis identifies *citation-hallucination* as the
top risk and generates a harness whose verifier re-fetches every URL in the
output to prove it exists.
"""

from __future__ import annotations

import asyncio

from aegis import Aegis


async def main() -> None:
    aegis = Aegis()

    result = await aegis.run(
        "Find 3 well-known open-source LLM agent frameworks. "
        "For each, provide the project name, the GitHub URL, and a one-line description."
    )

    print("=" * 72)
    print(" RESULT")
    print("=" * 72)
    print(result.to_json())

    print("\n" + "=" * 72)
    print(" GENERATED HARNESS")
    print("=" * 72)
    print(result.harness_code)


if __name__ == "__main__":
    asyncio.run(main())
