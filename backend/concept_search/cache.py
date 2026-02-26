"""Generic async LRU cache with TTL and in-flight deduplication."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")

# Registry of all cache instances for bulk clear
_all_caches: list[LRUCache] = []  # type: ignore[type-arg]


@dataclass
class _CacheEntry(Generic[V]):
    """A cached value with creation timestamp."""

    created: float
    value: V


@dataclass
class LRUCache(Generic[K, V]):
    """Async LRU cache with TTL and in-flight deduplication.

    - Entries expire after ``ttl_seconds``.
    - When ``max_size`` is reached the oldest entry is evicted.
    - Concurrent calls for the same key share a single computation.

    All instances are registered for bulk clearing via ``clear_all()``.
    """

    name: str
    hits: int = 0
    max_size: int = 10_000
    misses: int = 0
    ttl_seconds: float = 86400.0
    _cache: dict[K, _CacheEntry[V]] = field(default_factory=dict)
    _in_flight: dict[K, asyncio.Event] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        """Register this cache instance for bulk clearing."""
        _all_caches.append(self)

    async def get_or_compute(
        self,
        key: K,
        compute: Callable[[], Awaitable[V]],
    ) -> V:
        """Return a cached value or compute it.

        Args:
            key: The cache key (must be hashable).
            compute: An async callable that produces the value on cache miss.

        Returns:
            Cached or freshly-computed value.
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry and (time.monotonic() - entry.created) < self.ttl_seconds:
                self.hits += 1
                self._cache[key] = self._cache.pop(key)
                logger.debug("%s hit key=%s", self.name, key)
                return entry.value

            event = self._in_flight.get(key)
            if event is not None:
                pass  # fall through to await below
            else:
                event = asyncio.Event()
                self._in_flight[key] = event
                event = None  # signal that we are the owner

        if event is not None:
            await event.wait()
            async with self._lock:
                entry = self._cache.get(key)
                if entry and (time.monotonic() - entry.created) < self.ttl_seconds:
                    self.hits += 1
                    self._cache[key] = self._cache.pop(key)
                    return entry.value

        self.misses += 1
        logger.debug("%s miss key=%s", self.name, key)
        success = False
        try:
            value = await compute()
            success = True
        finally:
            async with self._lock:
                if success and self.max_size > 0:
                    if len(self._cache) >= self.max_size:
                        oldest = next(iter(self._cache))
                        del self._cache[oldest]
                    self._cache[key] = _CacheEntry(
                        created=time.monotonic(), value=value
                    )
                ev = self._in_flight.pop(key, None)
                if ev is not None:
                    ev.set()

        return value

    async def clear(self) -> int:
        """Remove all cached entries and reset counters.

        Returns:
            Number of entries that were cleared.
        """
        async with self._lock:
            n = len(self._cache)
            self._cache.clear()
            self.hits = 0
            self.misses = 0
            return n

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        return {
            "hit_rate": round(self.hits / total, 3) if total else 0,
            "hits": self.hits,
            "misses": self.misses,
            "size": len(self._cache),
        }


async def clear_all() -> dict[str, int]:
    """Clear all registered cache instances.

    Returns:
        Dict mapping cache name to number of entries cleared.
    """
    results = {}
    for cache in _all_caches:
        results[cache.name] = await cache.clear()
    return results
