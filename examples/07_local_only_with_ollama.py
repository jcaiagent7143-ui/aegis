"""Example 07 — Fully offline run via a local Ollama server.

Pre-reqs::

    brew install ollama   # or follow https://ollama.com
    ollama pull llama3.1
    ollama serve          # starts on http://localhost:11434

Then::

    python examples/07_local_only_with_ollama.py
"""

from __future__ import annotations

import asyncio

from aegis import Aegis
from aegis.providers import Ollama


async def main() -> None:
    aegis = Aegis(provider=Ollama(model="llama3.1"))
    result = await aegis.run(
        "Compute the sum of the first 50 positive integers, and show your work."
    )
    print(result.to_json())
    print(result.harness_code)


if __name__ == "__main__":
    asyncio.run(main())
