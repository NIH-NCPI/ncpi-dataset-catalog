"""Resolve agent — grounds a single mention against the concept index."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import ConceptIndex
from .models import ConceptMatch, RawMention, ResolveResult

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "RESOLVE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[ConceptIndex, ResolveResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# In-memory LRU cache for resolved mentions
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    """A cached resolve result with creation timestamp."""

    created: float
    result: ResolveResult


@dataclass
class _ResolveCache:
    """LRU cache with TTL and in-flight deduplication for resolve results.

    - Keys are ``(facet, normalized_text)`` tuples.
    - Entries expire after ``ttl_seconds`` (default 24 h).
    - When ``max_size`` is reached the oldest entry is evicted.
    - Concurrent resolves for the same key share a single LLM call.
    """

    hits: int = 0
    max_size: int = 10_000
    misses: int = 0
    ttl_seconds: float = 86400.0
    _cache: dict[tuple[str, str], _CacheEntry] = field(
        default_factory=dict
    )
    _in_flight: dict[tuple[str, str], asyncio.Event] = field(
        default_factory=dict
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @staticmethod
    def _make_key(mention: RawMention) -> tuple[str, str]:
        """Build a normalized cache key from a mention."""
        return (mention.facet.value, mention.text.strip().lower())

    async def get_or_resolve(
        self,
        mention: RawMention,
        index: ConceptIndex,
        model: str | None,
    ) -> ResolveResult:
        """Return a cached result or resolve via the LLM.

        Args:
            mention: The raw mention to resolve.
            index: ConceptIndex to search against.
            model: Optional model override.

        Returns:
            Cached or freshly-resolved ResolveResult.
        """
        key = self._make_key(mention)

        async with self._lock:
            # 1. Cache hit?
            entry = self._cache.get(key)
            if entry and (time.monotonic() - entry.created) < self.ttl_seconds:
                self.hits += 1
                # Move to end for LRU ordering
                self._cache[key] = self._cache.pop(key)
                logger.info("resolve_cache hit key=%s", key)
                return entry.result

            # 2. Another coroutine already resolving this key?
            event = self._in_flight.get(key)
            if event is not None:
                # Wait outside the lock for the in-flight resolve
                pass  # fall through to await below
            else:
                # 3. We own this resolve — mark in-flight
                event = asyncio.Event()
                self._in_flight[key] = event
                event = None  # signal that we are the owner

        # --- Outside the lock ---

        if event is not None:
            # We are a waiter — wait for the owner to finish
            await event.wait()
            async with self._lock:
                entry = self._cache.get(key)
                if entry:
                    self.hits += 1
                    self._cache[key] = self._cache.pop(key)
                    return entry.result
            # Owner failed or entry expired — fall through to resolve
            # (rare edge case; just do a fresh resolve)

        # We are the owner (or fallback) — call the LLM
        self.misses += 1
        logger.info("resolve_cache miss key=%s", key)
        try:
            result = await _run_resolve_uncached(mention, index, model)
        finally:
            async with self._lock:
                ev = self._in_flight.pop(key, None)
                if ev is not None:
                    ev.set()

        # Store result
        async with self._lock:
            if len(self._cache) >= self.max_size:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = _CacheEntry(
                created=time.monotonic(), result=result
            )

        return result

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


resolve_cache = _ResolveCache(
    max_size=int(os.environ.get("RESOLVE_CACHE_MAX_SIZE", "10000")),
    ttl_seconds=float(os.environ.get("RESOLVE_CACHE_TTL_SECONDS", "86400")),
)


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[ConceptIndex, ResolveResult]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    with _lock:
        if _agent is None or model != _agent_model:
            _agent_model = model
            _agent = Agent(
                model,
                output_type=ResolveResult,
                system_prompt=_load_prompt(),
                deps_type=ConceptIndex,
                model_settings=ModelSettings(
                    anthropic_cache_instructions=True,
                    anthropic_cache_tool_definitions=True,
                    temperature=0.0,
                ),
            )

            @_agent.tool
            def search_concepts(
                ctx: RunContext[ConceptIndex],
                query: str,
                facet: str | None = None,
                limit: int = 20,
            ) -> list[ConceptMatch]:
                """Search the concept index for matching values.

                Use this for measurement and consentCode facets. For focus
                facets, prefer get_focus_category_terms instead.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    query: Search string (case-insensitive substring match).
                    facet: Optional facet to restrict search (e.g. "measurement",
                           "focus", "consentCode").
                    limit: Maximum results to return.

                Returns:
                    List of matching concepts with study counts.
                """
                return ctx.deps.search_concepts(query, facet=facet, limit=limit)

            @_agent.tool
            def get_focus_category_terms(
                ctx: RunContext[ConceptIndex],
                category: str,
            ) -> list[ConceptMatch]:
                """Get all focus/disease terms in a MeSH category.

                Use this for focus facet mentions. First identify the right
                category from the list in the prompt, then call this tool
                to see all terms in that category and pick the best match.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    category: Category name (e.g. "Cardiovascular Diseases",
                             "Neoplasms", "Nervous System Diseases").

                Returns:
                    All focus terms in the category, sorted by study count.
                """
                return ctx.deps.get_focus_category_terms(category)

            @_agent.tool
            def get_consent_code_categories(
                ctx: RunContext[ConceptIndex],
            ) -> dict:
                """Get the top-level consent code categories and modifiers.

                Call this first for any consentCode mention. Returns base
                codes (GRU, HMB, DS, etc.) with descriptions and study
                counts, plus modifier definitions (IRB, NPU, etc.).

                Args:
                    ctx: Run context with ConceptIndex dependency.

                Returns:
                    Dict with 'base_codes' and 'modifiers' lists.
                """
                return ctx.deps.get_consent_code_categories()

            @_agent.tool
            def get_disease_specific_codes(
                ctx: RunContext[ConceptIndex],
            ) -> list[dict]:
                """Get all disease-specific (DS-*) consent code categories.

                Call this when the mention refers to a disease or condition.
                Returns disease abbreviations with full names and study counts.

                Args:
                    ctx: Run context with ConceptIndex dependency.

                Returns:
                    Disease codes with abbreviations, names, and study counts.
                """
                return ctx.deps.get_disease_specific_codes()

            @_agent.tool
            def get_consent_codes_for_base(
                ctx: RunContext[ConceptIndex],
                base_code: str,
                limit: int = 20,
            ) -> list[dict]:
                """Get all consent code variants for a base code prefix.

                Call this to see all variants of a base code (e.g. all
                GRU-* variants, or all DS-CVD-* variants with modifiers).

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    base_code: Base code prefix (e.g. "GRU", "HMB", "DS-CVD").
                    limit: Maximum results to return.

                Returns:
                    Matching codes with study counts.
                """
                return ctx.deps.get_consent_codes_for_base(base_code, limit=limit)

            @_agent.tool
            def compute_consent_eligibility(
                ctx: RunContext[ConceptIndex],
                purpose: str = "general",
                disease: str | None = None,
                is_nonprofit: bool | None = None,
                explicit_code: str | None = None,
                disease_only: bool = False,
            ) -> dict:
                """Compute all consent codes eligible for a research use case.

                Use this for consentCode mentions. Single tool call — handles
                both explicit codes and eligibility use cases.

                Two modes:
                - **explicit_code**: prefix-matches a code (e.g. "GRU" →
                  GRU, GRU-IRB, GRU-NPU).
                - **purpose**: "general", "health", or "disease". GRU is
                  always eligible; HMB for health/disease; DS-X when the
                  user's disease matches X.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    purpose: "general", "health", or "disease".
                    disease: Disease name or abbreviation (e.g. "diabetes",
                        "DIAB", "cancer", "CA", "type 1 diabetes", "T1D").
                        Automatically resolved to the correct abbreviation.
                    is_nonprofit: True or None includes all codes; False
                        excludes codes with NPU modifier.
                    explicit_code: Consent code to prefix-match (e.g. "GRU",
                        "HMB", "DS-CVD"). Overrides purpose logic.
                    disease_only: True when the user says "only",
                        "specifically", or "disease-specific". Restricts
                        results to DS-* codes only (excludes GRU, HMB, etc.).

                Returns:
                    Dict with 'eligible_codes' list and 'total_codes' count.
                """
                all_values = ctx.deps.list_facet_values("consentCode")
                all_codes = [m.value for m in all_values]
                # Resolve disease name to abbreviation if needed
                resolved_disease = None
                if disease:
                    resolved_disease = resolve_disease_name(disease)
                eligible = compute_eligible_codes(
                    all_codes,
                    purpose=purpose,
                    disease=resolved_disease,
                    is_nonprofit=is_nonprofit,
                    explicit_code=explicit_code,
                    disease_only=disease_only,
                )
                return {
                    "eligible_codes": eligible,
                    "resolved_disease": resolved_disease,
                    "total_codes": len(all_codes),
                }

            @_agent.tool
            def get_measurement_category_concepts(
                ctx: RunContext[ConceptIndex],
                top_level: str,
                mid_level: str | None = None,
            ) -> list[ConceptMatch]:
                """Get measurement concepts in a hierarchy category.

                Use this for measurement facet mentions. First identify the
                top-level category from the list in the prompt (e.g.
                "Cardiovascular"), then optionally drill into a mid-level
                (e.g. "Blood Pressure") to see specific concepts.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    top_level: Top-level category (e.g. "Cardiovascular").
                    mid_level: Optional mid-level subcategory (e.g. "Blood
                              Pressure"). If omitted, returns all concepts
                              in the top-level.

                Returns:
                    Measurement concepts in the category, sorted by study count.
                """
                return ctx.deps.get_measurement_category_concepts(
                    top_level, mid_level
                )

        return _agent


async def _run_resolve_uncached(
    mention: RawMention,
    index: ConceptIndex,
    model: str | None = None,
) -> ResolveResult:
    """Call the LLM to resolve a mention (no caching).

    Args:
        mention: The raw mention to resolve.
        index: ConceptIndex to search against.
        model: Override the model (default: Haiku).

    Returns:
        ResolveResult with canonical value(s).
    """
    agent = _get_agent(model)
    prompt = f"Resolve this mention:\n- text: {mention.text}\n- facet: {mention.facet.value}"
    result = await agent.run(prompt, deps=index)
    return result.output


async def run_resolve(
    mention: RawMention,
    index: ConceptIndex,
    model: str | None = None,
) -> ResolveResult:
    """Resolve a single raw mention to canonical index values.

    Results are cached by ``(facet, normalized_text)`` to avoid redundant
    LLM calls for repeated mentions.

    Args:
        mention: The raw mention to resolve.
        index: ConceptIndex to search against.
        model: Override the model (default: Haiku).

    Returns:
        ResolveResult with canonical value(s).
    """
    return await resolve_cache.get_or_resolve(mention, index, model)
