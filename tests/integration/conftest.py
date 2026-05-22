"""Fixtures for VCR-recorded integration tests.

Each cassette captures the full HTTP interaction for a single test, including
the JSON request/response bodies. Re-record by deleting the cassette and
re-running with ``RUN_LIVE_TESTS=1`` and a valid API key in env.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _filter_headers(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    redact = {"authorization", "x-api-key", "openai-organization", "cookie", "set-cookie"}
    return [(k, "REDACTED" if k.lower() in redact else v) for k, v in headers]


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "record_mode": "new_episodes" if os.environ.get("RUN_LIVE_TESTS") else "none",
        "filter_headers": ["authorization", "x-api-key", "openai-organization", "cookie"],
        "filter_post_data_parameters": ["api_key"],
        "match_on": ["method", "scheme", "host", "port", "path"],  # body match is too brittle
        "before_record_response": _scrub_response,
    }


def _scrub_response(response: dict[str, Any]) -> dict[str, Any]:
    response["headers"] = dict(_filter_headers(list(response.get("headers", {}).items())))
    return response


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip live tests unless RUN_LIVE_TESTS=1 in env."""
    if os.environ.get("RUN_LIVE_TESTS"):
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE_TESTS=1 and a provider key to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
