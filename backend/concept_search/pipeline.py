"""Three-agent pipeline: Extract → (Resolve + Structure) → Merge.

The controller orchestrates three independent agents:
  1. **Extract** — parse mentions from the query (sequential, must run first)
  2. **Resolve** — fill in catalog values for each mention (parallel per mention)
  3. **Structure** — determine boolean logic / exclude flags (parallel with resolve)

Resolve and Structure run concurrently because Structure only needs the
(facet, original_text) from Extract — not the resolved values.  A deterministic
merge step zips the resolved values onto the structure's exclude flags.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from .cache import LRUCache
from .extract_agent import run_extract
from .index import ConceptIndex, get_index
from .models import (
    SMALL_FACETS,
    QueryModel,
    ResolvedMention,
)
from .resolve_agent import run_resolve
from .structure_agent import run_structure

logger = logging.getLogger(__name__)

pipeline_cache: LRUCache[str, QueryModel] = LRUCache(
    name="pipeline_cache",
    max_size=int(os.environ.get("PIPELINE_CACHE_MAX_SIZE", "10000")),
    ttl_seconds=float(os.environ.get("PIPELINE_CACHE_TTL_SECONDS", "86400")),
)


# ---------------------------------------------------------------------------
# Resolve step (parallel per mention)
# ---------------------------------------------------------------------------


async def _resolve_all(
    mentions: list,
    index: ConceptIndex,
    model: str | None,
) -> tuple[list[ResolvedMention], list[str]]:
    """Resolve all mentions, running API calls in parallel.

    Returns (resolved_mentions, clarification_messages).
    """
    messages: list[str] = []

    # Separate pre-resolved (small facets) from those needing API calls
    needs_resolve: list[tuple[int, object]] = []
    for i, mention in enumerate(mentions):
        if mention.facet in SMALL_FACETS and mention.values:
            logger.debug("  %r: pre-resolved %s", mention.text, mention.values)
        else:
            needs_resolve.append((i, mention))

    # Fire all resolve calls in parallel
    resolve_results: dict[int, object] = {}
    if needs_resolve:
        coros = [run_resolve(m, index, model=model) for _, m in needs_resolve]
        results = await asyncio.gather(*coros)
        for (i, _), result in zip(needs_resolve, results, strict=True):
            resolve_results[i] = result

    # Reassemble in original order
    resolved: list[ResolvedMention] = []
    for i, mention in enumerate(mentions):
        if mention.facet in SMALL_FACETS and mention.values:
            resolved.append(
                ResolvedMention(
                    facet=mention.facet,
                    original_text=mention.text,
                    values=mention.values,
                )
            )
        else:
            rr = resolve_results[i]
            logger.debug("  %r: resolved to %s", mention.text, rr.values)
            resolved.append(
                ResolvedMention(
                    disambiguation=rr.disambiguation,
                    facet=mention.facet,
                    matched_variables=rr.matched_variables or [],
                    original_text=mention.text,
                    values=rr.values,
                )
            )
            if rr.message:
                messages.append(rr.message)

    return resolved, messages


# ---------------------------------------------------------------------------
# Structure step (placeholder values — only needs facet + original_text)
# ---------------------------------------------------------------------------


async def _structure(
    query: str,
    mentions: list,
    model: str | None,
) -> QueryModel:
    """Run structure agent with placeholder values.

    Structure only determines exclude flags from the query semantics.
    It doesn't need resolved values, so we pass empty value lists.
    """
    placeholder_mentions = [
        ResolvedMention(
            facet=m.facet,
            original_text=m.text,
            values=m.values if (m.facet in SMALL_FACETS and m.values) else [],
        )
        for m in mentions
    ]
    return await run_structure(query, placeholder_mentions, model=model)


# ---------------------------------------------------------------------------
# Deterministic merge
# ---------------------------------------------------------------------------


def _merge(
    resolved: list[ResolvedMention],
    structure: QueryModel,
) -> QueryModel:
    """Merge resolved values onto the structure's exclude flags.

    The structure agent returns mentions with exclude flags set but
    placeholder values.  This step zips the actual resolved values in.
    """
    # Build lookup: (facet, original_text) -> exclude flag from structure
    exclude_flags: dict[tuple[str, str], bool] = {}
    for m in structure.mentions:
        exclude_flags[(m.facet.value, m.original_text)] = m.exclude

    merged: list[ResolvedMention] = []
    for m in resolved:
        key = (m.facet.value, m.original_text)
        merged.append(
            ResolvedMention(
                disambiguation=m.disambiguation,
                exclude=exclude_flags.get(key, False),
                facet=m.facet,
                matched_variables=m.matched_variables,
                original_text=m.original_text,
                values=m.values,
            )
        )

    return QueryModel(mentions=merged)


# ---------------------------------------------------------------------------
# Multi-turn merge
# ---------------------------------------------------------------------------


def _merge_with_previous(
    previous: QueryModel,
    new_mentions: list[ResolvedMention],
    new_intent: str | None = None,
) -> QueryModel:
    """Merge new resolved mentions onto a previous QueryModel.

    Args:
        previous: The previous query state (from the client round-trip).
        new_mentions: Newly resolved mentions from the current turn.
        new_intent: Intent from the new extraction. If provided and not
            the default ``"study"``, overrides the previous intent.

    Returns:
        Merged QueryModel with previous + new mentions. If the same
        ``(facet, original_text)`` appears in both, the new mention wins.
    """
    # Index previous mentions by (facet, original_text)
    by_key: dict[tuple[str, str], ResolvedMention] = {}
    for m in previous.mentions:
        by_key[(m.facet.value, m.original_text)] = m

    # New mentions overwrite previous on collision
    for m in new_mentions:
        by_key[(m.facet.value, m.original_text)] = m

    # Determine intent: new extraction wins only if explicitly changed
    # from the default ("study").  The extract agent returns "study" by
    # default, so we must not let that silently clobber a prior "variable".
    intent = new_intent if new_intent and new_intent != "study" else previous.intent

    return QueryModel(
        intent=intent,
        mentions=list(by_key.values()),
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def _run_pipeline_uncached(
    query: str,
    index: ConceptIndex | None = None,
    model: str | None = None,
    previous_query: QueryModel | None = None,
) -> QueryModel:
    """Run the full 3-agent pipeline (no caching).

    Args:
        query: The user's natural-language search query.
        index: ConceptIndex to use. If None, uses the shared singleton.
        model: Override the model for all agents.
        previous_query: Previous query state for multi-turn refinement.

    Returns:
        Structured QueryModel with resolved mentions and boolean logic.
    """
    if index is None:
        index = get_index()

    # --- Step 1: Extract (sequential — must run first) ---
    t0 = time.monotonic()
    extract_result = await run_extract(query, model=model, previous_query=previous_query)
    t_extract = time.monotonic()
    logger.info(
        "Extract: %.0fms, %d mentions",
        (t_extract - t0) * 1000,
        len(extract_result.mentions),
    )

    intent = extract_result.intent
    logger.info("Intent: %s", intent)

    # In refine mode with no new mentions, return previous with preserved intent.
    # Only override intent if the extract agent returned something other than
    # the default "study" (which it always emits, even when user didn't change it).
    if not extract_result.mentions and previous_query:
        preserved_intent = intent if intent != "study" else previous_query.intent
        return QueryModel(
            intent=preserved_intent,
            mentions=previous_query.mentions,
            message=extract_result.message,
        )

    if not extract_result.mentions:
        return QueryModel(
            intent=intent,
            mentions=[],
            message=extract_result.message,
        )

    messages: list[str] = []
    if extract_result.message:
        messages.append(extract_result.message)

    # --- Step 2: Resolve + Structure (parallel) ---
    t_par0 = time.monotonic()
    (resolved, resolve_msgs), structure_result = await asyncio.gather(
        _resolve_all(extract_result.mentions, index, model),
        _structure(query, extract_result.mentions, model),
    )
    t_par = time.monotonic()
    logger.info("Resolve+Structure (parallel): %.0fms", (t_par - t_par0) * 1000)
    messages.extend(resolve_msgs)

    # --- Step 3: Deterministic merge ---
    new_merged = _merge(resolved, structure_result)

    if previous_query:
        query_model = _merge_with_previous(previous_query, new_merged.mentions, new_intent=intent)
    else:
        query_model = new_merged
        query_model.intent = intent

    for m in query_model.mentions:
        logger.debug(
            "  %s %s: %s",
            "NOT" if m.exclude else "AND",
            m.facet.value,
            m.values,
        )

    if messages:
        query_model.message = " ".join(messages)

    return query_model


async def run_pipeline(
    query: str,
    index: ConceptIndex | None = None,
    model: str | None = None,
    previous_query: QueryModel | None = None,
) -> QueryModel:
    """Run the full 3-agent pipeline on a natural-language query.

    Results are cached by normalized query string. A cache hit skips
    all three agents (extract, resolve, structure). Cache is bypassed
    for multi-turn requests (session-specific, near-zero hit rate).

    Args:
        query: The user's natural-language search query.
        index: ConceptIndex to use. If None, uses the shared singleton.
        model: Override the model for all agents.
        previous_query: Previous query state for multi-turn refinement.

    Returns:
        Structured QueryModel with resolved mentions and boolean logic.
    """
    # Skip pipeline cache for multi-turn (session-specific state).
    # Per-mention resolve cache still works.
    if previous_query:
        return await _run_pipeline_uncached(query, index, model, previous_query=previous_query)

    key = query.strip().lower()
    return await pipeline_cache.get_or_compute(
        key, lambda: _run_pipeline_uncached(query, index, model)
    )
