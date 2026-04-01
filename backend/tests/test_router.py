"""Eval tests for the router agent — calls the real LLM.

These tests verify that the router classifies follow-up messages
correctly given active filters. They require ANTHROPIC_API_KEY.

Run: cd backend && uv run python -m pytest tests/test_router.py -x -q
"""

from __future__ import annotations

import os

import pytest

from concept_search.models import Facet, QueryModel, ResolvedMention

# Skip entire module if no API key is set.
if not os.environ.get("ANTHROPIC_API_KEY"):
    pytest.skip("ANTHROPIC_API_KEY not set — skipping LLM evals", allow_module_level=True)

from concept_search.router_agent import run_router  # noqa: E402


def _rm(facet: Facet, text: str, values: list[str]) -> ResolvedMention:
    """Shorthand for creating a resolved mention."""
    return ResolvedMention(facet=facet, original_text=text, values=values, exclude=False)


# -- Test cases: (description, previous_query, follow_up, expected_kind) --

CASES: list[tuple[str, QueryModel, str, str]] = [
    (
        "additive fragment with 'also' should route to refine",
        QueryModel(
            intent="study",
            mentions=[_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])],
        ),
        "also where BMI was measured",
        "refine",
    ),
    (
        "additive fragment with 'and' should route to refine",
        QueryModel(
            intent="study",
            mentions=[
                _rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"]),
                _rm(Facet.DATA_TYPE, "transcriptomic", ["Transcriptomic"]),
            ],
        ),
        "and on AnVIL",
        "refine",
    ),
    (
        "additive fragment 'only in females' should route to refine",
        QueryModel(
            intent="study",
            mentions=[_rm(Facet.FOCUS, "cancer", ["Cancer"])],
        ),
        "only in females",
        "refine",
    ),
    (
        "complete standalone query should route to reset",
        QueryModel(
            intent="study",
            mentions=[_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])],
        ),
        "show me COPD studies on BDC",
        "reset",
    ),
    (
        "explicit replacement should route to replace",
        QueryModel(
            intent="study",
            mentions=[_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])],
        ),
        "change diabetes to asthma",
        "replace",
    ),
    (
        "removal request should route to remove",
        QueryModel(
            intent="study",
            mentions=[
                _rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"]),
                _rm(Facet.PLATFORM, "AnVIL", ["AnVIL"]),
            ],
        ),
        "remove the AnVIL filter",
        "remove",
    ),
    (
        "additive measurement refinement should stay add, not reset",
        QueryModel(
            intent="study",
            mentions=[
                _rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"]),
                _rm(Facet.DATA_TYPE, "transcriptomic", ["Transcriptomic"]),
            ],
        ),
        "also where BMI was measured",
        "refine",
    ),
]


@pytest.mark.evals
@pytest.mark.parametrize(
    "description,previous_query,follow_up,expected_kind",
    CASES,
    ids=[c[0] for c in CASES],
)
async def test_router_classification(
    description: str,
    previous_query: QueryModel,
    follow_up: str,
    expected_kind: str,
) -> None:
    """Verify the router LLM classifies the follow-up correctly."""
    result = await run_router(follow_up, previous_query)
    assert result.kind == expected_kind, (
        f"Router classified '{follow_up}' as '{result.kind}', expected '{expected_kind}'. "
        f"Full result: {result}"
    )
