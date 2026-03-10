"""Eval harness for the router agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .models import (
    DisambiguationOption,
    Facet,
    QueryModel,
    ResolvedMention,
    RouteAdd,
    RouteRemove,
    RouteReplace,
    RouteReset,
    RouteSelect,
    RouterResult,
)
from .router_agent import run_router


# ---------------------------------------------------------------------------
# Input model for eval cases
# ---------------------------------------------------------------------------

class RouterInput(BaseModel):
    """Input to the router eval: a follow-up message + previous query state."""

    previous_query: QueryModel
    query: str


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _disambig_previous() -> QueryModel:
    """Previous query with a disambiguation-pending glucose mention + resolved diabetes."""
    return QueryModel(
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text="diabetes",
                values=["Diabetes Mellitus"],
            ),
            ResolvedMention(
                disambiguation=[
                    DisambiguationOption(
                        concept_id="phenx:fasting_plasma_glucose_blood_draw",
                        label="Blood glucose measurement (Biomarkers)",
                    ),
                    DisambiguationOption(
                        concept_id="topmed:nutrient_intake",
                        label="Dietary glucose intake (Diet)",
                    ),
                ],
                facet=Facet.MEASUREMENT,
                original_text="glucose",
                values=[],
            ),
        ],
    )


def _resolved_previous() -> QueryModel:
    """Previous query with resolved mentions (no disambiguation pending)."""
    return QueryModel(
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text="diabetes",
                values=["Diabetes Mellitus"],
            ),
            ResolvedMention(
                facet=Facet.MEASUREMENT,
                original_text="blood pressure",
                values=["topmed:bp_systolic", "topmed:bp_diastolic"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class RouterEvaluator(Evaluator[RouterInput, RouterResult]):
    """Scores router output against expected route classification.

    Scoring:
    - kind must match exactly (0 or 1)
    - For select: recall on selected_ids
    - For remove: recall on original_texts
    - For replace: exact match on original_text, fuzzy on new_text
    - For reset: fuzzy match on new_query (contains key terms)
    - For add: kind match is sufficient
    """

    def evaluate(
        self, ctx: EvaluatorContext[RouterInput, RouterResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        scores: dict[str, float] = {}

        # Kind must match
        if expected is None:
            scores["route_score"] = 1.0 if actual.kind == "add" else 0.0
            return scores

        if actual.kind != expected.kind:
            scores["route_score"] = 0.0
            return scores

        # Kind-specific scoring
        if expected.kind == "select" and isinstance(expected, RouteSelect):
            actual_select = actual  # type: ignore[assignment]
            exp_ids = {v.lower() for v in expected.selected_ids}
            act_ids = {v.lower() for v in actual_select.selected_ids}
            if not act_ids:
                scores["route_score"] = 0.0
            else:
                recall = len(exp_ids & act_ids) / len(exp_ids)
                scores["route_score"] = round(recall, 3)

        elif expected.kind == "remove" and isinstance(expected, RouteRemove):
            actual_remove = actual  # type: ignore[assignment]
            exp_texts = {t.lower() for t in expected.original_texts}
            act_texts = {t.lower() for t in actual_remove.original_texts}
            if not act_texts:
                scores["route_score"] = 0.0
            else:
                recall = len(exp_texts & act_texts) / len(exp_texts)
                scores["route_score"] = round(recall, 3)

        elif expected.kind == "replace" and isinstance(expected, RouteReplace):
            actual_replace = actual  # type: ignore[assignment]
            orig_match = expected.original_text.lower() in actual_replace.original_text.lower()
            new_match = expected.new_text.lower() in actual_replace.new_text.lower()
            scores["route_score"] = 1.0 if (orig_match and new_match) else 0.5 if orig_match else 0.0

        elif expected.kind == "reset" and isinstance(expected, RouteReset):
            actual_reset = actual  # type: ignore[assignment]
            # Check that key terms from expected appear in actual
            exp_words = set(expected.new_query.lower().split())
            act_words = set(actual_reset.new_query.lower().split())
            # At least half the expected words should appear
            overlap = len(exp_words & act_words) / len(exp_words) if exp_words else 1.0
            scores["route_score"] = round(min(overlap * 2, 1.0), 3)

        else:
            # add — kind match is sufficient
            scores["route_score"] = 1.0

        return scores


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

dataset = Dataset[RouterInput, RouterResult, RouterResult](
    evaluators=[RouterEvaluator()],
    cases=[
        # --- Disambiguation pending ---
        Case(
            name="select-first",
            inputs=RouterInput(
                query="blood glucose",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteSelect(
                selected_ids=["phenx:fasting_plasma_glucose_blood_draw"],
            ),
        ),
        Case(
            name="select-multiple",
            inputs=RouterInput(
                query="both blood glucose and dietary",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteSelect(
                selected_ids=[
                    "phenx:fasting_plasma_glucose_blood_draw",
                    "topmed:nutrient_intake",
                ],
            ),
        ),
        Case(
            name="shorthand-1",
            inputs=RouterInput(
                query="the first one",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteSelect(
                selected_ids=["phenx:fasting_plasma_glucose_blood_draw"],
            ),
        ),
        Case(
            name="shorthand-2",
            inputs=RouterInput(
                query="2",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteSelect(
                selected_ids=["topmed:nutrient_intake"],
            ),
        ),
        Case(
            name="replace-disambig",
            inputs=RouterInput(
                query="actually I meant meat consumption",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteReplace(
                original_text="glucose",
                new_text="meat consumption",
            ),
        ),
        Case(
            name="reject-all",
            inputs=RouterInput(
                query="forget about glucose",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteRemove(original_texts=["glucose"]),
        ),
        Case(
            name="neither",
            inputs=RouterInput(
                query="neither",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteRemove(original_texts=["glucose"]),
        ),
        Case(
            name="add-with-disambig",
            inputs=RouterInput(
                query="also on AnVIL",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="reset-with-disambig",
            inputs=RouterInput(
                query="show me COPD studies instead",
                previous_query=_disambig_previous(),
            ),
            expected_output=RouteReset(new_query="COPD studies"),
        ),
        # --- No disambiguation pending ---
        Case(
            name="add-no-disambig",
            inputs=RouterInput(
                query="also on AnVIL",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="remove-via-chat",
            inputs=RouterInput(
                query="remove the diabetes filter",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteRemove(original_texts=["diabetes"]),
        ),
        Case(
            name="replace-via-chat",
            inputs=RouterInput(
                query="change diabetes to asthma",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReplace(
                original_text="diabetes",
                new_text="asthma",
            ),
        ),
        Case(
            name="reset-no-disambig",
            inputs=RouterInput(
                query="show me COPD studies",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReset(new_query="COPD studies"),
        ),
        Case(
            name="add-sex-filter",
            inputs=RouterInput(
                query="only in females",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="reset-unrelated",
            inputs=RouterInput(
                query="what about sleep data?",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReset(new_query="sleep data"),
        ),
        # --- Add within same facet ---
        Case(
            name="add-and-same-facet",
            inputs=RouterInput(
                query="and asthma",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="add-or-same-facet",
            inputs=RouterInput(
                query="or asthma",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="add-also-measurement",
            inputs=RouterInput(
                query="also BMI",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        Case(
            name="add-additional-focus",
            inputs=RouterInput(
                query="include heart disease too",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteAdd(),
        ),
        # --- Standalone queries should reset, not add ---
        Case(
            name="reset-standalone-query",
            inputs=RouterInput(
                query="show me studies with BMI data",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReset(new_query="studies with BMI data"),
        ),
        Case(
            name="reset-full-sentence",
            inputs=RouterInput(
                query="I want to find lung cancer studies on BDC",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReset(new_query="lung cancer studies on BDC"),
        ),
        Case(
            name="reset-new-criteria",
            inputs=RouterInput(
                query="studies where participants have COPD and are over 65",
                previous_query=_resolved_previous(),
            ),
            expected_output=RouteReset(
                new_query="studies where participants have COPD and are over 65",
            ),
        ),
    ],
)


async def _run_task(inputs: RouterInput) -> RouterResult:
    return await run_router(inputs.query, inputs.previous_query)


async def run_evals() -> None:
    """Run the router eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running router evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
