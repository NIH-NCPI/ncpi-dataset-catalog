"""Unit tests for the generic LRU cache."""

from __future__ import annotations

import asyncio

import pytest

from concept_search.cache import LRUCache, _all_caches, clear_all


@pytest.fixture()
def cache() -> LRUCache[str, str]:
    """Return a small, short-TTL cache for testing."""
    c = LRUCache[str, str](name="test", max_size=3, ttl_seconds=1.0)
    yield c
    # Remove from global registry so tests don't leak
    _all_caches.remove(c)


async def _compute(value: str) -> str:
    """Trivial async compute function."""
    return value


@pytest.mark.asyncio()
async def test_cache_hit(cache: LRUCache[str, str]) -> None:
    """Second call for the same key should return cached result."""
    call_count = 0

    async def counted() -> str:
        nonlocal call_count
        call_count += 1
        return "hello"

    r1 = await cache.get_or_compute("k", counted)
    r2 = await cache.get_or_compute("k", counted)
    assert r1 == r2 == "hello"
    assert call_count == 1
    assert cache.hits == 1
    assert cache.misses == 1


@pytest.mark.asyncio()
async def test_different_keys_are_separate(
    cache: LRUCache[str, str],
) -> None:
    """Different keys should produce separate cache entries."""
    call_count = 0

    async def counted() -> str:
        nonlocal call_count
        call_count += 1
        return "v"

    await cache.get_or_compute("a", counted)
    await cache.get_or_compute("b", counted)
    assert call_count == 2
    assert cache.misses == 2


@pytest.mark.asyncio()
async def test_ttl_expiration() -> None:
    """Entries should expire after TTL seconds."""
    cache = LRUCache[str, str](name="ttl-test", max_size=100, ttl_seconds=0.05)
    call_count = 0

    async def counted() -> str:
        nonlocal call_count
        call_count += 1
        return "v"

    await cache.get_or_compute("k", counted)
    await asyncio.sleep(0.1)
    await cache.get_or_compute("k", counted)
    assert call_count == 2
    assert cache.misses == 2
    _all_caches.remove(cache)


@pytest.mark.asyncio()
async def test_lru_eviction(cache: LRUCache[str, str]) -> None:
    """When max_size is reached, the oldest entry should be evicted."""
    for k in ["a", "b", "c"]:
        await cache.get_or_compute(k, lambda: _compute(k))
    assert len(cache._cache) == 3

    await cache.get_or_compute("d", lambda: _compute("d"))
    assert len(cache._cache) == 3
    assert "a" not in cache._cache


@pytest.mark.asyncio()
async def test_lru_access_refreshes(cache: LRUCache[str, str]) -> None:
    """Accessing an entry should move it to the end (most recent)."""
    for k in ["a", "b", "c"]:
        await cache.get_or_compute(k, lambda: _compute(k))
    # Access "a" to refresh it
    await cache.get_or_compute("a", lambda: _compute("a"))
    # Adding "d" should now evict "b" (the oldest untouched)
    await cache.get_or_compute("d", lambda: _compute("d"))
    assert "a" in cache._cache
    assert "b" not in cache._cache


@pytest.mark.asyncio()
async def test_in_flight_deduplication(cache: LRUCache[str, str]) -> None:
    """Concurrent computes for the same key should run only once."""
    call_count = 0

    async def slow() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return "v"

    results = await asyncio.gather(
        cache.get_or_compute("k", slow),
        cache.get_or_compute("k", slow),
        cache.get_or_compute("k", slow),
    )
    assert call_count == 1
    assert all(r == "v" for r in results)


@pytest.mark.asyncio()
async def test_clear(cache: LRUCache[str, str]) -> None:
    """clear() should empty the cache and reset counters."""
    await cache.get_or_compute("a", lambda: _compute("a"))
    await cache.get_or_compute("a", lambda: _compute("a"))
    assert cache.hits == 1
    n = await cache.clear()
    assert n == 1
    assert cache.hits == 0
    assert cache.misses == 0
    assert len(cache._cache) == 0


@pytest.mark.asyncio()
async def test_stats(cache: LRUCache[str, str]) -> None:
    """stats property should report accurate metrics."""
    await cache.get_or_compute("a", lambda: _compute("a"))
    await cache.get_or_compute("a", lambda: _compute("a"))
    await cache.get_or_compute("b", lambda: _compute("b"))
    stats = cache.stats
    assert stats["hits"] == 1
    assert stats["misses"] == 2
    assert stats["size"] == 2
    assert stats["hit_rate"] == pytest.approx(0.333, abs=0.01)


@pytest.mark.asyncio()
async def test_tuple_keys() -> None:
    """Cache should work with tuple keys (used by resolve cache)."""
    cache = LRUCache[tuple[str, str], str](name="tuple-test", max_size=10)
    r1 = await cache.get_or_compute(("focus", "diabetes"), lambda: _compute("v1"))
    r2 = await cache.get_or_compute(("focus", "diabetes"), lambda: _compute("v2"))
    r3 = await cache.get_or_compute(("measurement", "diabetes"), lambda: _compute("v3"))
    assert r1 == r2 == "v1"  # cache hit
    assert r3 == "v3"  # different key
    assert cache.hits == 1
    assert cache.misses == 2
    _all_caches.remove(cache)


@pytest.mark.asyncio()
async def test_compute_exception_not_cached(cache: LRUCache[str, str]) -> None:
    """Failed computes should not be cached, and retries should work."""

    async def failing() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await cache.get_or_compute("k", failing)

    assert len(cache._cache) == 0
    assert "k" not in cache._in_flight

    # Retry should succeed
    r = await cache.get_or_compute("k", lambda: _compute("ok"))
    assert r == "ok"
    assert len(cache._cache) == 1


@pytest.mark.asyncio()
async def test_in_flight_exception_propagates(cache: LRUCache[str, str]) -> None:
    """When the owner fails, waiters should retry (not get a stale error)."""
    call_count = 0

    async def slow_fail() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        raise RuntimeError("boom")

    results = await asyncio.gather(
        cache.get_or_compute("k", slow_fail),
        cache.get_or_compute("k", slow_fail),
        return_exceptions=True,
    )

    # Owner fails; waiter falls through and also calls compute
    assert all(isinstance(r, RuntimeError) for r in results)
    assert len(cache._cache) == 0


@pytest.mark.asyncio()
async def test_clear_all() -> None:
    """clear_all() should clear all registered caches."""
    c1 = LRUCache[str, str](name="c1", max_size=10)
    c2 = LRUCache[str, str](name="c2", max_size=10)
    await c1.get_or_compute("a", lambda: _compute("a"))
    await c2.get_or_compute("b", lambda: _compute("b"))

    results = await clear_all()
    assert results["c1"] == 1
    assert results["c2"] == 1
    assert len(c1._cache) == 0
    assert len(c2._cache) == 0
    _all_caches.remove(c1)
    _all_caches.remove(c2)
