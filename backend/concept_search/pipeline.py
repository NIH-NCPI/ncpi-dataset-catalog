"""Three-agent pipeline: Extract → Resolve → Structure."""

from __future__ import annotations

import asyncio
import logging

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


async def run_pipeline(
    query: str,
    index: ConceptIndex | None = None,
    model: str | None = None,
) -> QueryModel:
    """Run the full 3-agent pipeline on a natural-language query.

    Args:
        query: The user's natural-language search query.
        index: ConceptIndex to use. If None, uses the shared singleton.
        model: Override the model for all agents.

    Returns:
        Structured QueryModel with resolved mentions and boolean logic.
    """
    if index is None:
        index = get_index()

    # --- Step 1: Extract ---
    logger.debug("Step 1: Extract mentions")
    extract_result = await run_extract(query, model=model)
    logger.debug("Extracted %d mentions", len(extract_result.mentions))
    for m in extract_result.mentions:
        logger.debug("  %s: %r values=%s", m.facet.value, m.text, m.values)

    # Collect clarification messages from agents
    messages: list[str] = []

    if not extract_result.mentions:
        return QueryModel(
            mentions=[],
            message=extract_result.message,
        )

    if extract_result.message:
        messages.append(extract_result.message)

    # --- Step 2: Resolve (parallel) ---
    logger.debug("Step 2: Resolve mentions")
    resolved: list[ResolvedMention] = []

    # Separate pre-resolved (small facets) from those needing API calls
    needs_resolve: list[tuple[int, object]] = []
    for i, mention in enumerate(extract_result.mentions):
        if mention.facet in SMALL_FACETS and mention.values:
            logger.debug("  %r: pre-resolved %s", mention.text, mention.values)
        else:
            needs_resolve.append((i, mention))

    # Fire all resolve calls in parallel
    resolve_results: dict[int, object] = {}
    if needs_resolve:
        coros = [run_resolve(m, index, model=model) for _, m in needs_resolve]
        results = await asyncio.gather(*coros)
        for (i, _), result in zip(needs_resolve, results):
            resolve_results[i] = result

    # Reassemble in original order
    for i, mention in enumerate(extract_result.mentions):
        if mention.facet in SMALL_FACETS and mention.values:
            resolved.append(
                ResolvedMention(
                    facet=mention.facet,
                    original_text=mention.text,
                    values=mention.values,
                )
            )
        else:
            resolve_result = resolve_results[i]
            logger.debug(
                "  %r: resolved to %s", mention.text, resolve_result.values
            )
            resolved.append(
                ResolvedMention(
                    facet=mention.facet,
                    original_text=mention.text,
                    values=resolve_result.values,
                )
            )
            if resolve_result.message:
                messages.append(resolve_result.message)

    # --- Step 3: Structure ---
    logger.debug("Step 3: Structure query logic")
    query_model = await run_structure(query, resolved, model=model)
    logger.debug("Final query: %d mentions", len(query_model.mentions))
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
