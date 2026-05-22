"""Example 02 — Code task: the harness includes an AST validator + test-runner.

Run with::

    python examples/02_code_refactor.py
"""

from __future__ import annotations

import asyncio

from aegis import Aegis


async def main() -> None:
    aegis = Aegis()

    result = await aegis.run(
        "Look at examples/sample_module.py. Suggest a refactor that splits "
        "the `process()` function into smaller helpers. Return: the new file "
        "content, a one-paragraph rationale, and a list of behaviors preserved."
    )

    print(result.to_json())
    print("\n--- harness ---")
    print(result.harness_code)


if __name__ == "__main__":
    asyncio.run(main())
