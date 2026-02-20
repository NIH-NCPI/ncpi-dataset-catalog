"""Sliding-window per-IP rate limiter (in-memory)."""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque


class RateLimiter:
    """In-memory sliding-window rate limiter keyed by client IP.

    Parameters
    ----------
    max_requests:
        Maximum requests allowed per window.  Falls back to the
        ``RATE_LIMIT_MAX_REQUESTS`` env var, then ``10``.
    window_seconds:
        Length of the sliding window in seconds.  Falls back to the
        ``RATE_LIMIT_WINDOW_SECONDS`` env var, then ``60``.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float | None = None,
    ) -> None:
        if max_requests is None:
            max_requests = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "10"))
        if window_seconds is None:
            window_seconds = float(
                os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")
            )
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        """Return ``True`` if *key* is within the rate limit."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            dq = self._hits.get(key)
            if dq is None:
                dq = deque()
                self._hits[key] = dq

            # Expire old timestamps
            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= self.max_requests:
                return False

            dq.append(now)
            return True

    async def cleanup(self) -> None:
        """Remove empty deques to prevent unbounded memory growth."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            empty_keys = []
            for key, dq in self._hits.items():
                while dq and dq[0] <= cutoff:
                    dq.popleft()
                if not dq:
                    empty_keys.append(key)
            for key in empty_keys:
                del self._hits[key]
