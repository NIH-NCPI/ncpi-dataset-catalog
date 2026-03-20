# PRD: Resolve Agent Result Cache

## Problem

The resolve agent maps natural-language mentions to canonical catalog values by calling Claude Haiku. Every mention of a `focus`, `measurement`, or `consentCode` facet triggers an LLM call — even when the exact same `(facet, text)` pair was resolved moments ago.

For example, if three different users each search for "diabetes studies", the resolve agent calls the LLM three separate times to arrive at the same answer: `["Diabetes Mellitus"]`.

### Impact

| Metric                           | Without cache  | With cache (warm)               |
| -------------------------------- | -------------- | ------------------------------- |
| Latency per mention              | 50–200 ms      | < 1 ms                          |
| Haiku tokens per mention         | ~500–1,500     | 0                               |
| Cost per 1,000 identical queries | ~1,500K tokens | ~1,500 tokens (first call only) |

Common queries cluster heavily around a small vocabulary: disease names ("diabetes", "cancer", "asthma"), measurements ("blood pressure", "BMI"), and consent codes ("GRU", "HMB"). A warm cache would eliminate the vast majority of redundant LLM calls in practice.

## Proposed Solution

Add an **in-memory LRU cache** in front of the resolve agent's LLM call. The cache key is `(facet, normalized_text)` and the cached value is the `ResolveResult`.

### Cache Key Design

```
key = (mention.facet.value, mention.text.strip().lower())
```

Examples:

- `("focus", "diabetes")` → `ResolveResult(values=["Diabetes Mellitus"], message=None)`
- `("measurement", "blood pressure")` → `ResolveResult(values=["Systolic Blood Pressure"], message=None)`
- `("consentCode", "gru")` → `ResolveResult(values=["GRU"], message=None)`

### Behavior

1. Before calling the LLM, check the cache for `(facet, normalized_text)`.
2. **Cache hit** → return the cached `ResolveResult` immediately.
3. **Cache miss** → call the LLM as today, store the result, return it.

### Cache Invalidation

- **TTL:** Entries expire after a configurable duration (default: 24 hours). This bounds staleness after catalog rebuilds.
- **Manual flush:** `POST /admin/cache/clear` endpoint (or a startup flag) for use after `make db-reload`.
- **Catalog rebuild:** The cache should auto-clear when the server restarts (which `make db-reload` already does).
- **Max size:** LRU eviction at 10,000 entries (each entry is tiny — a few hundred bytes).

### What NOT to cache

- Mentions where the resolve agent returns a `message` (clarification/ambiguity). These indicate the agent wasn't fully confident, and re-resolving may produce different results as the user refines their query. **(Open question — see below.)**

## Scope

### In Scope

- In-memory `dict`-based LRU cache in `resolve_agent.py`
- Cache key normalization (lowercase, strip whitespace)
- TTL-based expiration
- `/admin/cache/clear` endpoint
- Logging: cache hit/miss events with timing
- Metrics: hit rate, miss rate surfaced in `/search` response timing

### Out of Scope (potential follow-ups)

- Persistent cache (Redis, SQLite, disk) — not needed until we validate the hit rate
- Cache warming on startup from eval fixtures or historical queries
- Distributed cache for multi-instance deployments
- Pre-seeding from the eval test suite (258 known mappings)

## Open Questions

1. **Should we cache results that include a `message`?** These indicate ambiguity ("Could also mean HDL Cholesterol..."). Caching them avoids re-resolving, but the message was generated for a specific context. Recommendation: cache them — the message is still useful and the values are the same.

2. **Should temperature be lowered to 0.0?** This would make caching fully deterministic. Trade-off: temperature 0.2 allows the agent to explore alternative disambiguation paths, which may produce better results for edge cases. Recommendation: keep 0.2 for now — the cache makes determinism less important since we lock in the first result.

3. **Cache scope: per-process or shared?** In-memory means per-process. If we run multiple workers (e.g., uvicorn with `--workers 4`), each has its own cache. This is fine for now — the server runs single-worker today.

## Success Criteria

- **Hit rate > 30%** in the first week of production usage (measured via logging)
- **P50 latency reduction** for repeated queries: from ~150 ms to < 1 ms per cached mention
- **No regression** in resolve accuracy (eval suite passes identically)
- **Cache miss path** is identical to today's behavior (no behavior change for novel queries)

## Implementation Notes

- Touch only `resolve_agent.py` (and `api.py` for the admin endpoint)
- Use Python's `functools.lru_cache` or a simple `dict` with TTL wrapper — no new dependencies
- The cache sits inside `run_resolve()`, wrapping the `agent.run()` call
- Thread-safe: use the existing `_lock` or `asyncio.Lock` since resolve is called via `asyncio.gather`
