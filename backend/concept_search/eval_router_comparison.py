"""A/B comparison: current router (Haiku) vs conversation-aware spike (Sonnet).

Runs both routers against the existing 24 eval cases plus new conversation-aware
cases, then prints a side-by-side comparison using pydantic_evals.

Usage:
    cd backend && uv run python -m concept_search.eval_router_comparison
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_evals import Case, Dataset

from .api_models import ConversationMessage
from .eval_router import RouterEvaluator
from .eval_router import dataset as baseline_dataset
from .models import (
    Facet,
    QueryModel,
    ResolvedMention,
    RouteRefine,
    RouterResult,
)
from .router_agent import run_router as run_router_haiku
from .router_spike import run_router as run_router_spike

# ---------------------------------------------------------------------------
# Extended input model that includes conversation history
# ---------------------------------------------------------------------------


class SpikeRouterInput(BaseModel):
    """Input to the spike router eval: follow-up + state + conversation."""

    messages: list[ConversationMessage] = []
    previous_query: QueryModel
    query: str


# ---------------------------------------------------------------------------
# Test fixtures for conversation-aware scenarios
# ---------------------------------------------------------------------------


def _disease_previous() -> QueryModel:
    """Previous query with a resolved disease focus."""
    return QueryModel(
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text="diabetes",
                values=["Diabetes Mellitus"],
            ),
        ],
    )


def _disease_platform_previous() -> QueryModel:
    """Previous query with disease focus + platform."""
    return QueryModel(
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text="diabetes",
                values=["Diabetes Mellitus"],
            ),
            ResolvedMention(
                facet=Facet.PLATFORM,
                original_text="AnVIL",
                values=["AnVIL"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Conversation-aware test cases
# ---------------------------------------------------------------------------

# These cases include conversation history that provides context the current
# router doesn't have.  The expected output is RouteRefine — the current
# router may misclassify some as RouteReset because they look like standalone
# queries without conversational context.

conversation_cases: list[Case[SpikeRouterInput, RouterResult, RouterResult]] = [
    Case(
        name="consent-eligibility-after-disease",
        inputs=SpikeRouterInput(
            query="what can I use?",
            previous_query=_disease_previous(),
            messages=[
                ConversationMessage(role="user", content="diabetes studies"),
                ConversationMessage(
                    role="assistant",
                    content="Found 45 diabetes studies across 3 platforms.",
                ),
            ],
        ),
        expected_output=RouteRefine(),
    ),
    Case(
        name="eligibility-full-sentence",
        inputs=SpikeRouterInput(
            query="which of these am I eligible to use for my research?",
            previous_query=_disease_previous(),
            messages=[
                ConversationMessage(role="user", content="diabetes studies"),
                ConversationMessage(
                    role="assistant",
                    content="Found 45 diabetes studies across 3 platforms.",
                ),
            ],
        ),
        expected_output=RouteRefine(),
    ),
    Case(
        name="pronoun-reference-refine",
        inputs=SpikeRouterInput(
            query="are there any with blood pressure data?",
            previous_query=_disease_platform_previous(),
            messages=[
                ConversationMessage(role="user", content="diabetes studies on AnVIL"),
                ConversationMessage(
                    role="assistant",
                    content="Found 12 diabetes studies on AnVIL.",
                ),
            ],
        ),
        expected_output=RouteRefine(),
    ),
    Case(
        name="how-about-modifier",
        inputs=SpikeRouterInput(
            query="how about in women?",
            previous_query=QueryModel(
                mentions=[
                    ResolvedMention(
                        facet=Facet.FOCUS,
                        original_text="heart disease",
                        values=["Heart Diseases"],
                    ),
                ],
            ),
            messages=[
                ConversationMessage(role="user", content="heart disease studies"),
                ConversationMessage(
                    role="assistant",
                    content="Found 30 heart disease studies.",
                ),
            ],
        ),
        expected_output=RouteRefine(),
    ),
    Case(
        name="only-narrowing",
        inputs=SpikeRouterInput(
            query="only the ones with WGS",
            previous_query=_disease_platform_previous(),
            messages=[
                ConversationMessage(role="user", content="diabetes studies on AnVIL"),
                ConversationMessage(
                    role="assistant",
                    content="Found 12 diabetes studies on AnVIL.",
                ),
            ],
        ),
        expected_output=RouteRefine(),
    ),
]


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

# Combined dataset: existing 24 cases (no messages) + 5 new conversation cases.
# We use SpikeRouterInput for all cases — existing ones just have empty messages.
all_cases: list[Case[SpikeRouterInput, RouterResult, RouterResult]] = []

for case in baseline_dataset.cases:
    # Wrap existing RouterInput cases as SpikeRouterInput (no messages).
    all_cases.append(
        Case(
            name=case.name,
            inputs=SpikeRouterInput(
                messages=[],
                previous_query=case.inputs.previous_query,
                query=case.inputs.query,
            ),
            expected_output=case.expected_output,
        )
    )

all_cases.extend(conversation_cases)

combined_dataset = Dataset[SpikeRouterInput, RouterResult, RouterResult](
    evaluators=[RouterEvaluator()],
    cases=all_cases,
)


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------


async def _haiku_task(inputs: SpikeRouterInput) -> RouterResult:
    """Run the current Haiku router (ignores messages)."""
    return await run_router_haiku(inputs.query, inputs.previous_query)


async def _spike_task(inputs: SpikeRouterInput) -> RouterResult:
    """Run the spike Sonnet router (uses messages)."""
    return await run_router_spike(
        inputs.query,
        inputs.previous_query,
        messages=inputs.messages or None,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_comparison() -> None:
    """Run both routers and print A/B comparison."""
    print("Running Haiku router (baseline)...")
    haiku_report = await combined_dataset.evaluate(_haiku_task, name="haiku-router")

    print("\nRunning Sonnet spike router...")
    spike_report = await combined_dataset.evaluate(_spike_task, name="spike-router")

    print("\n" + "=" * 60)
    print("BASELINE: Haiku router")
    print("=" * 60)
    haiku_report.print()

    print("\n" + "=" * 60)
    print("COMPARISON: Spike router vs Haiku baseline")
    print("=" * 60)
    spike_report.print(baseline=haiku_report)


def main() -> None:
    """CLI entry point."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_comparison())


if __name__ == "__main__":
    main()
