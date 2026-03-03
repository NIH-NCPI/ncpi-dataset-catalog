"""Resolve agent — grounds a single mention against the concept index."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from .cache import LRUCache
from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import ConceptIndex
from .models import ConceptMatch, RawMention, ResolveResult

_PROMPT_PATH = Path(__file__).parent / "RESOLVE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[ConceptIndex, ResolveResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()

resolve_cache: LRUCache[tuple[str, str], ResolveResult] = LRUCache(
    name="resolve_cache",
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
                keyword: str,
            ) -> list[ConceptMatch]:
                """Search measurement concepts by keyword.

                Searches the index for concepts whose namespaced ID contains
                the keyword. Use this for measurement facet mentions.

                Examples:
                  keyword="blood_pressure" → topmed:bp_systolic, topmed:bp_diastolic
                  keyword="biomarkers" → ncpi:biomarkers and all concepts under it
                  keyword="media" → phenx:media_use
                  keyword="smoking" → phenx:..._smoking_status_..., topmed:current_smoker_baseline

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    keyword: Search term (e.g. "blood_pressure", "smoking",
                             "cholesterol"). Spaces are converted to underscores.

                Returns:
                    Matching measurement concepts sorted by study count.
                """
                return ctx.deps.get_measurement_category_concepts(keyword)

            @_agent.tool
            def search_concepts_by_embedding(
                ctx: RunContext[ConceptIndex],
                query: str,
                top_k: int = 10,
            ) -> list[dict]:
                """Search concept and archetype nodes by semantic similarity.

                Uses embedding KNN to find the most semantically similar
                concepts. Works well for lay terms ("blood sugar" → glucose),
                abbreviations ("eGFR"), and typos ("hematacrit").

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    query: Natural-language search query.
                    top_k: Number of results to return (default 10).

                Returns:
                    Top-K concepts with concept_id, name, description, type,
                    similarity score, and study_count.
                """
                return ctx.deps.search_concepts_by_embedding(query, top_k=top_k)

            @_agent.tool
            def get_concept_children(
                ctx: RunContext[ConceptIndex],
                concept_id: str,
            ) -> list[dict]:
                """Get child sub-concepts with names and descriptions.

                ALWAYS call this before returning a concept. If a child is
                a more specific match, return the child instead. Children
                with type="archetype" are leaf nodes — return directly
                without further drilling.

                Empty list means leaf concept — safe to return.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    concept_id: Parent concept to look up children for
                        (e.g. "topmed:food_frequency_questionnaire").

                Returns:
                    Child concepts with concept_id, name, description,
                    and study_count, sorted by study count.
                """
                return ctx.deps.get_concept_children(concept_id)

            @_agent.tool
            def list_variables_for_concept(
                ctx: RunContext[ConceptIndex],
                concept_id: str,
                limit: int = 200,
            ) -> list[dict]:
                """List distinct variables under a concept with descriptions.

                Use at leaf concepts (no children) to verify that specific
                variables match the user's query. Returns variable_name
                and description.

                Args:
                    ctx: Run context with ConceptIndex dependency.
                    concept_id: Concept to list variables for.
                    limit: Maximum number of variables to return.

                Returns:
                    Distinct variables with variable_name and description.
                """
                return ctx.deps.list_variables_for_concept(concept_id, limit=limit)

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
    key = (mention.facet.value, mention.text.strip().lower())
    return await resolve_cache.get_or_compute(
        key, lambda: _run_resolve_uncached(mention, index, model)
    )
