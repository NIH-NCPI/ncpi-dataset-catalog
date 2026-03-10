"""End-to-end eval — runs the full pipeline and verifies returned studies."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .api import _split_mentions as api_split_mentions
from .index import get_index
from .models import QueryModel
from .pipeline import run_pipeline


class PipelineOutput(BaseModel):
    """Captures both the query model and resulting studies."""

    query: QueryModel
    studies: list[dict[str, Any]]


class StudyExpectation(BaseModel):
    """What we expect about the returned studies."""

    min_studies: int = 1
    max_studies: int | None = None
    # Every study must have ALL of these values in the given facet field.
    all_have: dict[str, list[str]] = {}
    # Every study must have AT LEAST ONE of these values in the given facet field.
    any_have: dict[str, list[str]] = {}
    # No study should have any of these values in the given facet field.
    none_have: dict[str, list[str]] = {}


# Map facet field names to the study dict keys.
_FIELD_MAP: dict[str, str] = {
    "consentCode": "consentCodes",
    "dataType": "dataTypes",
    "focus": "focus",
    "measurement": "measurement",
    "platform": "platforms",
    "studyDesign": "studyDesigns",
}


def _get_study_values(study: dict, field: str) -> set[str]:
    """Extract a set of values from a study for a given facet field."""
    key = _FIELD_MAP.get(field, field)
    raw = study.get(key)
    if raw is None:
        return set()
    if isinstance(raw, list):
        vals = {v.lower() for v in raw}
    else:
        vals = {str(raw).lower()}
    # For consent codes, also include the base code (e.g. "gru" from "gru-irb").
    if field == "consentCode":
        vals |= {v.split("-")[0] for v in vals}
    return vals


def _score_studies(
    studies: list[dict[str, Any]],
    expected: StudyExpectation,
) -> dict[str, float]:
    """Score study results against expectations.

    Args:
        studies: Actual study results from the pipeline.
        expected: Expected study properties.

    Returns:
        Dict with ``pipeline_score`` between 0.0 and 1.0.
    """
    penalties = 0.0
    checks = 0

    # Check study count bounds.
    checks += 1
    if len(studies) < expected.min_studies:
        penalties += 1.0
    if expected.max_studies is not None:
        checks += 1
        if len(studies) > expected.max_studies:
            penalties += 1.0

    # Check all_have: every study must contain ALL listed values.
    for field, required_values in expected.all_have.items():
        req_lower = {v.lower() for v in required_values}
        for study in studies:
            checks += 1
            vals = _get_study_values(study, field)
            if not req_lower.issubset(vals):
                penalties += 1.0

    # Check any_have: every study must contain AT LEAST ONE value.
    for field, candidate_values in expected.any_have.items():
        cand_lower = {v.lower() for v in candidate_values}
        for study in studies:
            checks += 1
            vals = _get_study_values(study, field)
            if not cand_lower.intersection(vals):
                penalties += 1.0

    # Check none_have: no study should contain any listed value.
    for field, forbidden_values in expected.none_have.items():
        forb_lower = {v.lower() for v in forbidden_values}
        for study in studies:
            checks += 1
            vals = _get_study_values(study, field)
            if forb_lower.intersection(vals):
                penalties += 1.0

    score = max(0.0, 1.0 - penalties / checks) if checks > 0 else 1.0
    return {"pipeline_score": round(score, 3)}


class PipelineEvaluator(Evaluator[str, PipelineOutput]):
    """Scores the end-to-end pipeline by checking study result properties."""

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineOutput]
    ) -> dict[str, float]:
        expected: StudyExpectation | None = ctx.expected_output
        if expected is None:
            return {"pipeline_score": 1.0}
        return _score_studies(ctx.output.studies, expected)


dataset = Dataset[str, PipelineOutput, StudyExpectation](
    evaluators=[PipelineEvaluator()],
    cases=[
        Case(
            name="anvil-and-bdc",
            inputs="datasets hosted by AnVIL and BioData Catalyst",
            # Two separate platform mentions → AND: studies on BOTH.
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"platform": ["AnVIL", "BDC"]},
            ),
        ),
        Case(
            name="wgs-diabetes",
            inputs="WGS studies on diabetes",
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"dataType": ["WGS"]},
                any_have={"focus": [
                    "Diabetes Mellitus",
                    "Diabetes Mellitus, Type 1",
                    "Diabetes Mellitus, Type 2",
                    "Diabetic Retinopathy",
                ]},
            ),
        ),
        Case(
            name="negation-no-pediatric",
            inputs="heart disease studies but not pediatric",
            expected_output=StudyExpectation(
                min_studies=1,
                none_have={"focus": ["Pediatrics"]},
            ),
        ),
        Case(
            name="nonsense-zero-results",
            inputs="blorpquantz zibberflam studies",
            expected_output=StudyExpectation(
                min_studies=0,
                max_studies=0,
            ),
        ),
        Case(
            name="bdc-blood-pressure",
            inputs="BDC studies with blood pressure data",
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"platform": ["BDC"]},
            ),
        ),
        Case(
            name="gru-bmi",
            inputs="general research use studies with BMI",
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"consentCode": ["GRU"]},
            ),
        ),
    ],
)


async def _run_task(inputs: str) -> PipelineOutput:
    index = get_index()
    query_model = await run_pipeline(inputs)
    studies: list[dict] = []
    if query_model.mentions:
        include, exclude = api_split_mentions(query_model.mentions, index)
        studies = index.query_studies(include, exclude or None)
    return PipelineOutput(query=query_model, studies=studies)


# ---------------------------------------------------------------------------
# Multi-turn pipeline evals
# ---------------------------------------------------------------------------


class Turn(BaseModel):
    """A single turn in a multi-turn pipeline eval."""

    query: str = ""
    remove_facets: list[str] = []


class MultiTurnInput(BaseModel):
    """Input for multi-turn pipeline eval cases."""

    turns: list[Turn]


class MultiTurnPipelineEvaluator(Evaluator[MultiTurnInput, PipelineOutput]):
    """Scores multi-turn pipeline evals using the same study checks."""

    def evaluate(
        self, ctx: EvaluatorContext[MultiTurnInput, PipelineOutput]
    ) -> dict[str, float]:
        expected: StudyExpectation | None = ctx.expected_output
        if expected is None:
            return {"pipeline_score": 1.0}
        return _score_studies(ctx.output.studies, expected)


multi_turn_dataset = Dataset[MultiTurnInput, PipelineOutput, StudyExpectation](
    evaluators=[MultiTurnPipelineEvaluator()],
    cases=[
        Case(
            name="multi-turn-add-platform",
            inputs=MultiTurnInput(
                turns=[
                    Turn(query="heart disease studies"),
                    Turn(query="also on AnVIL"),
                ],
            ),
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"platform": ["AnVIL"]},
            ),
        ),
        Case(
            name="multi-turn-lookup-only-remove",
            inputs=MultiTurnInput(
                turns=[
                    Turn(query="WGS diabetes studies on AnVIL"),
                    Turn(query="", remove_facets=["platform"]),
                ],
            ),
            expected_output=StudyExpectation(
                min_studies=1,
                all_have={"dataType": ["WGS"]},
            ),
        ),
    ],
)


async def _run_multi_turn_task(inputs: MultiTurnInput) -> PipelineOutput:
    """Chain turns: each turn passes its QueryModel as previousQuery to the next."""
    index = get_index()
    query_model: QueryModel | None = None

    for turn in inputs.turns:
        if turn.query and query_model:
            # Refine mode
            query_model = await run_pipeline(
                turn.query, previous_query=query_model
            )
        elif query_model and not turn.query:
            # Lookup-only mode — apply remove_facets if specified
            if turn.remove_facets:
                remove_set = set(turn.remove_facets)
                query_model = QueryModel(
                    intent=query_model.intent,
                    mentions=[
                        m
                        for m in query_model.mentions
                        if m.facet.value not in remove_set
                    ],
                )
            # In lookup-only mode, query_model is used as-is for lookup
        else:
            # Fresh mode
            query_model = await run_pipeline(turn.query)

    assert query_model is not None
    studies: list[dict] = []
    if query_model.mentions:
        include, exclude = api_split_mentions(query_model.mentions, index)
        studies = index.query_studies(include, exclude or None)
    return PipelineOutput(query=query_model, studies=studies)


async def run_evals() -> None:
    """Run the pipeline eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()
    print("\n--- Multi-turn pipeline evals ---\n")
    mt_report = await multi_turn_dataset.evaluate(_run_multi_turn_task)
    mt_report.print()


def main() -> None:
    """CLI entry point for running pipeline evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
