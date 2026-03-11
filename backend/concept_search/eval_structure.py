"""Eval harness for the structure agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .models import Facet, QueryModel, ResolvedMention
from .structure_agent import run_structure

# The structure agent input is (query, mentions) but pydantic-evals needs a
# single input type. We use a wrapper.

StructureInput = dict  # {"query": str, "mentions": list[dict]}


class StructureEvaluator(Evaluator[StructureInput, QueryModel]):
    """Scores structure agent by checking exclude flags and mention preservation.

    Matching logic:
    - Each expected mention is matched to actual by facet + values.
    - Exclude flag must match.
    - Values and facets must be passed through unchanged.
    - Score = fraction of expected mentions correctly structured.
    """

    def evaluate(self, ctx: EvaluatorContext[StructureInput, QueryModel]) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None or not expected.mentions:
            return {"structure_score": 1.0 if not actual.mentions else 0.0}

        matched = 0.0
        used_actual: set[int] = set()

        for exp in expected.mentions:
            best_idx = -1
            best_score = 0.0
            for i, act in enumerate(actual.mentions):
                if i in used_actual:
                    continue
                score = _structure_similarity(exp, act)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score > 0:
                used_actual.add(best_idx)
                matched += best_score

        total = len(expected.mentions)
        return {"structure_score": round(matched / total, 3) if total > 0 else 1.0}


def _structure_similarity(expected: ResolvedMention, actual: ResolvedMention) -> float:
    """Score a single structure mention match (0.0 or 1.0).

    Checks facet, exclude flag, and that values are preserved.
    """
    if expected.facet != actual.facet:
        return 0.0
    if expected.exclude != actual.exclude:
        return 0.0
    # Check values are passed through (case-insensitive)
    exp_set = {v.lower() for v in expected.values}
    act_set = {v.lower() for v in actual.values}
    if exp_set != act_set:
        return 0.0
    return 1.0


def _m(
    original_text: str,
    facet: Facet,
    values: list[str],
    exclude: bool = False,
) -> ResolvedMention:
    """Shorthand for building expected mentions."""
    return ResolvedMention(
        exclude=exclude,
        facet=facet,
        original_text=original_text,
        values=values,
    )


def _input(query: str, mentions: list[ResolvedMention]) -> StructureInput:
    """Build a structure agent input dict."""
    return {
        "query": query,
        "mentions": [m.model_dump() for m in mentions],
    }


dataset = Dataset[StructureInput, QueryModel, QueryModel](
    evaluators=[StructureEvaluator()],
    cases=[
        # --- Simple AND (no exclusion) ---
        Case(
            name="simple-and",
            inputs=_input(
                "blood pressure and diabetes studies",
                [
                    _m("blood pressure", Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("blood pressure", Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ]
            ),
        ),
        # --- Negation ---
        Case(
            name="but-not",
            inputs=_input(
                "echocardiography studies but not transesophageal",
                [
                    _m("echocardiography", Facet.MEASUREMENT, ["Echocardiography"]),
                    _m("transesophageal", Facet.MEASUREMENT, ["Transesophageal Echocardiography"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("echocardiography", Facet.MEASUREMENT, ["Echocardiography"]),
                    _m(
                        "transesophageal",
                        Facet.MEASUREMENT,
                        ["Transesophageal Echocardiography"],
                        exclude=True,
                    ),
                ]
            ),
        ),
        Case(
            name="excluding",
            inputs=_input(
                "diabetes studies excluding cancer",
                [
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("cancer", Facet.FOCUS, ["Neoplasms"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("cancer", Facet.FOCUS, ["Neoplasms"], exclude=True),
                ]
            ),
        ),
        Case(
            name="without",
            inputs=_input(
                "WGS studies without pediatric",
                [
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("pediatric", Facet.FOCUS, ["Pediatrics"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("pediatric", Facet.FOCUS, ["Pediatrics"], exclude=True),
                ]
            ),
        ),
        # --- Same facet AND ---
        Case(
            name="same-facet-and",
            inputs=_input(
                "studies with both heart disease and diabetes",
                [
                    _m("heart disease", Facet.FOCUS, ["Heart Diseases"]),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("heart disease", Facet.FOCUS, ["Heart Diseases"]),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ]
            ),
        ),
        # --- Multi-facet passthrough ---
        Case(
            name="multi-facet-passthrough",
            inputs=_input(
                "GRU consented WGS from diabetic patients where vitamin K was measured",
                [
                    _m("GRU", Facet.CONSENT_CODE, ["GRU"]),
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("diabetic", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("vitamin K", Facet.MEASUREMENT, ["Vitamin K Intake"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("GRU", Facet.CONSENT_CODE, ["GRU"]),
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("diabetic", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("vitamin K", Facet.MEASUREMENT, ["Vitamin K Intake"]),
                ]
            ),
        ),
        # --- Same facet passthrough (no merging) ---
        Case(
            name="same-facet-no-merge",
            inputs=_input(
                "studies with WGS or WXS data",
                [
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("WXS", Facet.DATA_TYPE, ["WXS"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("WXS", Facet.DATA_TYPE, ["WXS"]),
                ]
            ),
        ),
        # --- Mixed negation and AND ---
        Case(
            name="mixed-negation",
            inputs=_input(
                "cholesterol studies on AnVIL but not pediatric",
                [
                    _m("cholesterol", Facet.MEASUREMENT, ["Total Cholesterol"]),
                    _m("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                    _m("pediatric", Facet.FOCUS, ["Pediatrics"]),
                ],
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("cholesterol", Facet.MEASUREMENT, ["Total Cholesterol"]),
                    _m("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                    _m("pediatric", Facet.FOCUS, ["Pediatrics"], exclude=True),
                ]
            ),
        ),
    ],
)


async def _run_task(inputs: StructureInput) -> QueryModel:
    query = inputs["query"]
    mentions = [ResolvedMention(**m) for m in inputs["mentions"]]
    return await run_structure(query, mentions)


async def run_evals() -> None:
    """Run the structure eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running structure evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
