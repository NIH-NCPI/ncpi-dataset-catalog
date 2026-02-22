"""Unit tests for the resolve agent in-memory cache."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from concept_search.models import Facet, RawMention, ResolveResult
from concept_search.resolve_agent import _ResolveCache


def _mention(text: str, facet: Facet = Facet.MEASUREMENT) -> RawMention:
    """Build a minimal RawMention for testing."""
    return RawMention(facet=facet, text=text, values=[])


def _result(values: list[str]) -> ResolveResult:
    """Build a ResolveResult with the given values."""
    return ResolveResult(values=values)


@pytest.fixture()
def cache() -> _ResolveCache:
    """Return a small, short-TTL cache for testing."""
    return _ResolveCache(max_size=3, ttl_seconds=1.0)


@pytest.fixture()
def mock_resolve() -> AsyncMock:
    """Patch _run_resolve_uncached to return a predictable result."""
    result = _result(["Body Mass Index"])
    with patch(
        "concept_search.resolve_agent._run_resolve_uncached",
        new_callable=AsyncMock,
        return_value=result,
    ) as mock:
        yield mock


@pytest.mark.asyncio()
async def test_cache_hit(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """Second call for the same key should return cached result."""
    mention = _mention("BMI")
    r1 = await cache.get_or_resolve(mention, index=None, model=None)  # type: ignore[arg-type]
    r2 = await cache.get_or_resolve(mention, index=None, model=None)  # type: ignore[arg-type]
    assert r1 == r2
    assert mock_resolve.call_count == 1
    assert cache.hits == 1
    assert cache.misses == 1


@pytest.mark.asyncio()
async def test_key_normalization(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """Keys should be case- and whitespace-normalized."""
    m1 = _mention("  BMI  ")
    m2 = _mention("bmi")
    await cache.get_or_resolve(m1, index=None, model=None)  # type: ignore[arg-type]
    await cache.get_or_resolve(m2, index=None, model=None)  # type: ignore[arg-type]
    assert mock_resolve.call_count == 1
    assert cache.hits == 1


@pytest.mark.asyncio()
async def test_different_facets_are_separate(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """Same text in different facets should be separate cache entries."""
    m1 = _mention("diabetes", Facet.MEASUREMENT)
    m2 = _mention("diabetes", Facet.FOCUS)
    await cache.get_or_resolve(m1, index=None, model=None)  # type: ignore[arg-type]
    await cache.get_or_resolve(m2, index=None, model=None)  # type: ignore[arg-type]
    assert mock_resolve.call_count == 2
    assert cache.misses == 2


@pytest.mark.asyncio()
async def test_ttl_expiration(mock_resolve: AsyncMock) -> None:
    """Entries should expire after TTL seconds."""
    cache = _ResolveCache(max_size=100, ttl_seconds=0.05)
    mention = _mention("BMI")
    await cache.get_or_resolve(mention, index=None, model=None)  # type: ignore[arg-type]
    await asyncio.sleep(0.1)
    await cache.get_or_resolve(mention, index=None, model=None)  # type: ignore[arg-type]
    assert mock_resolve.call_count == 2
    assert cache.misses == 2


@pytest.mark.asyncio()
async def test_lru_eviction(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """When max_size is reached, the oldest entry should be evicted."""
    # Fill cache to capacity (max_size=3)
    for name in ["a", "b", "c"]:
        await cache.get_or_resolve(_mention(name), index=None, model=None)  # type: ignore[arg-type]
    assert len(cache._cache) == 3

    # Adding a 4th should evict "a"
    await cache.get_or_resolve(_mention("d"), index=None, model=None)  # type: ignore[arg-type]
    assert len(cache._cache) == 3
    key_a = ("measurement", "a")
    assert key_a not in cache._cache


@pytest.mark.asyncio()
async def test_lru_access_refreshes(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """Accessing an entry should move it to the end (most recent)."""
    for name in ["a", "b", "c"]:
        await cache.get_or_resolve(_mention(name), index=None, model=None)  # type: ignore[arg-type]
    # Access "a" to refresh it
    await cache.get_or_resolve(_mention("a"), index=None, model=None)  # type: ignore[arg-type]
    # Adding "d" should now evict "b" (the oldest untouched)
    await cache.get_or_resolve(_mention("d"), index=None, model=None)  # type: ignore[arg-type]
    key_a = ("measurement", "a")
    key_b = ("measurement", "b")
    assert key_a in cache._cache
    assert key_b not in cache._cache


@pytest.mark.asyncio()
async def test_in_flight_deduplication(cache: _ResolveCache) -> None:
    """Concurrent resolves for the same key should make only one LLM call."""
    call_count = 0

    async def slow_resolve(*_args: object, **_kwargs: object) -> ResolveResult:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return _result(["Body Mass Index"])

    with patch(
        "concept_search.resolve_agent._run_resolve_uncached",
        side_effect=slow_resolve,
    ):
        mention = _mention("BMI")
        results = await asyncio.gather(
            cache.get_or_resolve(mention, index=None, model=None),  # type: ignore[arg-type]
            cache.get_or_resolve(mention, index=None, model=None),  # type: ignore[arg-type]
            cache.get_or_resolve(mention, index=None, model=None),  # type: ignore[arg-type]
        )

    assert call_count == 1
    assert all(r == _result(["Body Mass Index"]) for r in results)


@pytest.mark.asyncio()
async def test_clear(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """clear() should empty the cache and reset counters."""
    await cache.get_or_resolve(_mention("BMI"), index=None, model=None)  # type: ignore[arg-type]
    await cache.get_or_resolve(_mention("BMI"), index=None, model=None)  # type: ignore[arg-type]
    assert cache.hits == 1
    n = await cache.clear()
    assert n == 1
    assert cache.hits == 0
    assert cache.misses == 0
    assert len(cache._cache) == 0


@pytest.mark.asyncio()
async def test_stats(
    cache: _ResolveCache, mock_resolve: AsyncMock
) -> None:
    """stats property should report accurate metrics."""
    await cache.get_or_resolve(_mention("BMI"), index=None, model=None)  # type: ignore[arg-type]
    await cache.get_or_resolve(_mention("BMI"), index=None, model=None)  # type: ignore[arg-type]
    await cache.get_or_resolve(_mention("glucose"), index=None, model=None)  # type: ignore[arg-type]
    stats = cache.stats
    assert stats["hits"] == 1
    assert stats["misses"] == 2
    assert stats["size"] == 2
    assert stats["hit_rate"] == pytest.approx(0.333, abs=0.01)
