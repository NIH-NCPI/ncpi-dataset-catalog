"""Eval harness for the extract agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .extract_agent import run_extract
from .models import ExtractResult, Facet, RawMention


class ExtractEvaluator(Evaluator[str, ExtractResult]):
    """Scores extract agent output by comparing expected vs actual mentions.

    Matching logic:
    - Each expected mention is matched to the best actual mention.
    - Facet must match exactly.
    - For small facets (platform, dataType, studyDesign): values must match
      using recall (expected ⊆ actual).
    - For other facets: just checks facet assignment (text is informational).
    - Score = fraction of expected mentions correctly matched.
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, ExtractResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None or not expected.mentions:
            return {"extract_score": 1.0 if not actual.mentions else 0.0}

        matched = 0.0
        used_actual: set[int] = set()

        for exp in expected.mentions:
            best_idx = -1
            best_score = 0.0
            for i, act in enumerate(actual.mentions):
                if i in used_actual:
                    continue
                score = _extract_similarity(exp, act)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score > 0:
                used_actual.add(best_idx)
                matched += best_score

        total = len(expected.mentions)
        return {
            "extract_score": round(matched / total, 3) if total > 0 else 1.0
        }


def _extract_similarity(expected: RawMention, actual: RawMention) -> float:
    """Score a single extract mention match (0.0 to 1.0)."""
    if expected.facet != actual.facet:
        return 0.0
    # For small facets, check values using recall
    if expected.values:
        exp_set = {v.lower() for v in expected.values}
        act_set = {v.lower() for v in actual.values}
        if not act_set:
            return 0.0
        hits = exp_set & act_set
        return len(hits) / len(exp_set)
    # For large facets, facet match is sufficient
    return 1.0


def _rm(
    text: str,
    facet: Facet,
    values: list[str] | None = None,
) -> RawMention:
    """Shorthand for building expected raw mentions."""
    return RawMention(facet=facet, text=text, values=values or [])


dataset = Dataset[str, ExtractResult, ExtractResult](
    evaluators=[ExtractEvaluator()],
    cases=[
        # --- Facet classification ---
        Case(
            name="single-measurement",
            inputs="studies with BMI data",
            expected_output=ExtractResult(
                mentions=[_rm("body mass index", Facet.MEASUREMENT)]
            ),
        ),
        Case(
            name="two-facets",
            inputs="blood pressure and diabetes studies",
            expected_output=ExtractResult(
                mentions=[
                    _rm("blood pressure", Facet.MEASUREMENT),
                    _rm("diabetes", Facet.FOCUS),
                ]
            ),
        ),
        Case(
            name="multi-facet",
            inputs="GRU consented WGS from diabetic patients where vitamin K was measured",
            expected_output=ExtractResult(
                mentions=[
                    _rm("GRU", Facet.CONSENT_CODE),
                    _rm("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _rm("diabetic", Facet.FOCUS),
                    _rm("vitamin K", Facet.MEASUREMENT),
                ]
            ),
        ),
        # --- Small facet resolution ---
        Case(
            name="data-type-resolve",
            inputs="WGS studies with SBP",
            expected_output=ExtractResult(
                mentions=[
                    _rm("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _rm("systolic blood pressure", Facet.MEASUREMENT),
                ]
            ),
        ),
        Case(
            name="platform-resolve",
            inputs="AnVIL studies with sleep data",
            expected_output=ExtractResult(
                mentions=[
                    _rm("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                    _rm("sleep", Facet.MEASUREMENT),
                ]
            ),
        ),
        Case(
            name="study-design-resolve",
            inputs="case-control WGS studies",
            expected_output=ExtractResult(
                mentions=[
                    _rm("case-control", Facet.STUDY_DESIGN, ["Case-Control"]),
                    _rm("WGS", Facet.DATA_TYPE, ["WGS"]),
                ]
            ),
        ),
        # --- OR merge for small facets ---
        Case(
            name="or-small-facet",
            inputs="studies with WGS or WXS data and cholesterol",
            expected_output=ExtractResult(
                mentions=[
                    _rm("WGS or WXS", Facet.DATA_TYPE, ["WGS", "WXS"]),
                    _rm("cholesterol", Facet.MEASUREMENT),
                ]
            ),
        ),
        # --- Mention splitting ---
        Case(
            name="negation-split",
            inputs="echocardiography studies but not transesophageal",
            expected_output=ExtractResult(
                mentions=[
                    _rm("echocardiography", Facet.MEASUREMENT),
                    _rm("transesophageal echocardiography", Facet.MEASUREMENT),
                ]
            ),
        ),
        Case(
            name="same-facet-split",
            inputs="studies with both heart disease and diabetes",
            expected_output=ExtractResult(
                mentions=[
                    _rm("heart disease", Facet.FOCUS),
                    _rm("diabetes", Facet.FOCUS),
                ]
            ),
        ),
        # --- Text normalization ---
        Case(
            name="abbreviation-expansion",
            inputs="studies with BMI and SBP",
            expected_output=ExtractResult(
                mentions=[
                    # Just check facet assignment; text may vary
                    _rm("body mass index", Facet.MEASUREMENT),
                    _rm("systolic blood pressure", Facet.MEASUREMENT),
                ]
            ),
        ),
        Case(
            name="consent-code",
            inputs="HMB-IRB studies with smoking data",
            expected_output=ExtractResult(
                mentions=[
                    _rm("HMB-IRB", Facet.CONSENT_CODE),
                    _rm("smoking", Facet.MEASUREMENT),
                ]
            ),
        ),
        # --- Data type synonyms ---
        Case(
            name="dt-whole-genome",
            inputs="whole genome sequencing studies with diabetes",
            expected_output=ExtractResult(
                mentions=[
                    _rm("whole genome sequencing", Facet.DATA_TYPE, ["WGS"]),
                    _rm("diabetes", Facet.FOCUS),
                ]
            ),
        ),
        Case(
            name="dt-whole-exome",
            inputs="whole exome sequencing studies",
            expected_output=ExtractResult(
                mentions=[
                    _rm("whole exome sequencing", Facet.DATA_TYPE, ["WXS"]),
                ]
            ),
        ),
        Case(
            name="dt-exome",
            inputs="exome sequencing studies with BMI",
            expected_output=ExtractResult(
                mentions=[
                    _rm("exome sequencing", Facet.DATA_TYPE, ["WXS"]),
                    _rm("body mass index", Facet.MEASUREMENT),
                ]
            ),
        ),
        Case(
            name="dt-transcriptomic",
            inputs="transcriptomic data from cancer studies",
            expected_output=ExtractResult(
                mentions=[
                    _rm("transcriptomic", Facet.DATA_TYPE, ["RNA-Seq"]),
                    _rm("cancer", Facet.FOCUS),
                ]
            ),
        ),
        Case(
            name="dt-snp-array",
            inputs="SNP array studies on AnVIL",
            expected_output=ExtractResult(
                mentions=[
                    _rm("SNP array", Facet.DATA_TYPE, ["SNP Genotypes (Array)"]),
                    _rm("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                ]
            ),
        ),
        Case(
            name="dt-methylation",
            inputs="methylation studies with smoking data",
            expected_output=ExtractResult(
                mentions=[
                    _rm("methylation", Facet.DATA_TYPE, ["Methylation (CpG)"]),
                    _rm("smoking", Facet.MEASUREMENT),
                ]
            ),
        ),
        # --- Demographic facets ---
        Case(
            name="sex-female",
            inputs="studies with female participants",
            expected_output=ExtractResult(
                mentions=[_rm("female", Facet.SEX, ["Female"])]
            ),
        ),
        Case(
            name="race-ethnicity",
            inputs="African American cohorts with WGS",
            expected_output=ExtractResult(
                mentions=[
                    _rm(
                        "African American",
                        Facet.RACE_ETHNICITY,
                        ["Black or African American"],
                    ),
                    _rm("WGS", Facet.DATA_TYPE, ["WGS"]),
                ]
            ),
        ),
        Case(
            name="computed-ancestry",
            inputs="European ancestry diabetes studies",
            expected_output=ExtractResult(
                mentions=[
                    _rm("European ancestry", Facet.COMPUTED_ANCESTRY, ["European"]),
                    _rm("diabetes", Facet.FOCUS),
                ]
            ),
        ),
        Case(
            name="sex-and-platform",
            inputs="male participants on BDC",
            expected_output=ExtractResult(
                mentions=[
                    _rm("male", Facet.SEX, ["Male"]),
                    _rm("BDC", Facet.PLATFORM, ["BDC"]),
                ]
            ),
        ),
        Case(
            name="hispanic-studies",
            inputs="Hispanic or Latino cohorts with BMI data",
            expected_output=ExtractResult(
                mentions=[
                    _rm(
                        "Hispanic or Latino",
                        Facet.RACE_ETHNICITY,
                        ["Hispanic or Latino"],
                    ),
                    _rm("body mass index", Facet.MEASUREMENT),
                ]
            ),
        ),
    ],
)


async def _run_task(inputs: str) -> ExtractResult:
    return await run_extract(inputs)


async def run_evals() -> None:
    """Run the extract eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running extract evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
