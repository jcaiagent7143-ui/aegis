"""Shared fixtures."""

from __future__ import annotations

import json
from typing import Any

import pytest

from aegis.providers.mock import Mock


@pytest.fixture
def mock_provider() -> Mock:
    return Mock()


@pytest.fixture
def scripted_provider():
    """Factory that returns a Mock with a scripted response list."""

    def _make(responses: list[Any]) -> Mock:
        flat = [r if isinstance(r, str) else json.dumps(r) for r in responses]
        return Mock(responses=flat)

    return _make
