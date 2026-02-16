"""Resolve agent — grounds a single mention against the concept index."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from .index import ConceptIndex
from .models import ConceptMatch, RawMention, ResolveResult

_PROMPT_PATH = Path(__file__).parent / "RESOLVE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[ConceptIndex, ResolveResult] | None = None
_agent_model: str | None = None


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[ConceptIndex, ResolveResult]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    if _agent is None or model != _agent_model:
        _agent_model = model
        _agent = Agent(
            model,
            output_type=ResolveResult,
            system_prompt=_load_prompt(),
            deps_type=ConceptIndex,
            model_settings=ModelSettings(temperature=0.2),
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
