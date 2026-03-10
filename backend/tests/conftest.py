"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Disable the per-IP rate limiter for all tests."""
    with patch(
        "concept_search.api._rate_limiter.is_allowed",
        new_callable=AsyncMock,
        return_value=True,
    ):
        yield
