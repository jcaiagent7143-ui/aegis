"""Example 03 — Numeric/CSV task: the harness adds an arithmetic re-checker.

Run with::

    python examples/03_data_analysis.py
"""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from aegis import Aegis

SAMPLE_CSV = Path(__file__).parent / "sales.csv"


def ensure_sample() -> None:
    if SAMPLE_CSV.exists():
        return
    SAMPLE_CSV.write_text(
        "product,units,price,revenue\n"
        "alpha,12,9.99,119.88\n"
        "bravo,5,49.50,247.50\n"
        "charlie,33,2.50,82.50\n"
        "delta,1,999.00,999.00\n"
        "echo,7,12.00,84.00\n"
    )


async def main() -> None:
    ensure_sample()
    aegis = Aegis()
    result = await aegis.run(
        f"Read {SAMPLE_CSV}. Which product produced the highest revenue? "
        "Return the product name and the revenue value."
    )
    print(result.to_json())
    print("\n--- harness ---")
    print(result.harness_code)


if __name__ == "__main__":
    asyncio.run(main())
