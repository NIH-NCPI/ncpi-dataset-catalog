"""Resolve agent — grounds a single mention against the concept index."""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import ConceptIndex
from .models import ConceptMatch, RawMention, ResolveResult

_PROMPT_PATH = Path(__file__).parent / "RESOLVE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[ConceptIndex, ResolveResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


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
                    temperature=0.2,
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


async def run_resolve(
    mention: RawMention,
    index: ConceptIndex,
    model: str | None = None,
) -> ResolveResult:
    """Resolve a single raw mention to canonical index values.

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
