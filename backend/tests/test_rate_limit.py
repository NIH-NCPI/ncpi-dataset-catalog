"""Unit tests for the per-IP sliding-window rate limiter."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from concept_search.rate_limit import RateLimiter


@pytest.fixture
def limiter() -> RateLimiter:
    """A rate limiter allowing 3 requests per 1-second window."""
    return RateLimiter(max_requests=3, window_seconds=1.0)


async def test_within_limit(limiter: RateLimiter) -> None:
    """Requests within the limit are allowed."""
    for _ in range(3):
        assert await limiter.is_allowed("192.168.1.1") is True


async def test_over_limit(limiter: RateLimiter) -> None:
    """The request exceeding the limit is rejected."""
    for _ in range(3):
        await limiter.is_allowed("192.168.1.1")
    assert await limiter.is_allowed("192.168.1.1") is False


async def test_separate_ip_tracking(limiter: RateLimiter) -> None:
    """Each IP has its own independent counter."""
    for _ in range(3):
        await limiter.is_allowed("10.0.0.1")

    # 10.0.0.1 is exhausted
    assert await limiter.is_allowed("10.0.0.1") is False
    # 10.0.0.2 still has its full quota
    assert await limiter.is_allowed("10.0.0.2") is True


async def test_window_expiry(limiter: RateLimiter) -> None:
    """After the window elapses, requests are allowed again."""
    for _ in range(3):
        await limiter.is_allowed("192.168.1.1")
    assert await limiter.is_allowed("192.168.1.1") is False

    # Advance time past the window
    await asyncio.sleep(1.1)
    assert await limiter.is_allowed("192.168.1.1") is True


async def test_cleanup_removes_expired_entries() -> None:
    """cleanup() removes entries whose timestamps have all expired."""
    limiter = RateLimiter(max_requests=2, window_seconds=0.5)
    await limiter.is_allowed("old-ip")
    await asyncio.sleep(0.6)
    await limiter.cleanup()
    assert "old-ip" not in limiter._hits


async def test_env_defaults() -> None:
    """Env vars configure max_requests and window_seconds."""
    with patch.dict(
        "os.environ",
        {"RATE_LIMIT_MAX_REQUESTS": "5", "RATE_LIMIT_WINDOW_SECONDS": "30"},
    ):
        limiter = RateLimiter()
        assert limiter.max_requests == 5
        assert limiter.window_seconds == 30.0
