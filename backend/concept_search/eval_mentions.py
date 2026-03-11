"""Eval harness for the 3-agent pipeline using pydantic-evals."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .models import Facet, QueryModel, ResolvedMention
from .pipeline import run_pipeline


class MentionEvaluator(Evaluator[str, QueryModel]):
    """Scores mention extraction by comparing expected vs actual mentions.

    Matching logic:
    - Each expected mention is matched to the best actual mention by facet +
      value overlap.
    - Values are compared as case-insensitive sets using recall (expected ⊆
      actual). Extra values in actual are not penalized.
    - facet and exclude must match exactly.
    - original_text is informational, not scored.
    - Score = fraction of expected mentions correctly resolved.
    """

    def evaluate(self, ctx: EvaluatorContext[str, QueryModel]) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None or not expected.mentions:
            return {"mention_score": 1.0 if not actual.mentions else 0.0}

        matched = 0.0
        used_actual: set[int] = set()

        for exp_mention in expected.mentions:
            best_idx = -1
            best_score = 0.0
            for i, act_mention in enumerate(actual.mentions):
                if i in used_actual:
                    continue
                score = _mention_similarity(exp_mention, act_mention)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score > 0:
                used_actual.add(best_idx)
                matched += best_score

        total = len(expected.mentions)
        return {"mention_score": round(matched / total, 3) if total > 0 else 1.0}


def _mention_similarity(expected: ResolvedMention, actual: ResolvedMention) -> float:
    """Score a single mention match (0.0 to 1.0).

    Uses recall: all expected values must appear in actual.
    Extra values in actual are not penalized (the agent may reasonably
    expand a concept into related terms).
    """
    if expected.facet != actual.facet:
        return 0.0
    if expected.exclude != actual.exclude:
        return 0.0
    if not expected.values:
        # Expected empty values means we just check facet + exclude match
        return 1.0
    exp_set = {v.lower() for v in expected.values}
    act_set = {v.lower() for v in actual.values}
    if not act_set:
        return 0.0
    # Recall: fraction of expected values found in actual
    hits = exp_set & act_set
    return len(hits) / len(exp_set)


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


# --- Eval cases ---
# Expected values are grounded in actual concepts from the classification output.
# Values within a mention are OR. Mentions are AND unless exclude=True (NOT).

dataset = Dataset[str, QueryModel, QueryModel](
    evaluators=[MentionEvaluator()],
    cases=[
        Case(
            name="single-measurement",
            inputs="studies with BMI data",
            expected_output=QueryModel(
                mentions=[
                    _m("BMI", Facet.MEASUREMENT, ["Body Mass Index"]),
                ]
            ),
        ),
        Case(
            name="two-mentions",
            inputs="blood pressure and diabetes studies",
            expected_output=QueryModel(
                mentions=[
                    _m(
                        "blood pressure",
                        Facet.MEASUREMENT,
                        ["Systolic Blood Pressure"],
                    ),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ]
            ),
        ),
        Case(
            name="lay-term-glucose",
            inputs="blood sugar studies",
            expected_output=QueryModel(
                mentions=[
                    _m("blood sugar", Facet.MEASUREMENT, ["Fasting Glucose"]),
                ]
            ),
        ),
        Case(
            name="typo",
            inputs="systollic blood presure studies",
            expected_output=QueryModel(
                mentions=[
                    _m(
                        "systollic blood presure",
                        Facet.MEASUREMENT,
                        ["Systolic Blood Pressure"],
                    ),
                ]
            ),
        ),
        Case(
            name="abbreviation-data-type",
            inputs="WGS studies with SBP",
            expected_output=QueryModel(
                mentions=[
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("SBP", Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
                ]
            ),
        ),
        Case(
            name="multi-facet",
            inputs="GRU consented WGS from diabetic patients where vitamin K was measured",
            expected_output=QueryModel(
                mentions=[
                    _m("GRU", Facet.CONSENT_CODE, ["GRU"]),
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("diabetic", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("vitamin K", Facet.MEASUREMENT, ["Vitamin K Intake"]),
                ]
            ),
        ),
        Case(
            name="platform-and-category",
            inputs="AnVIL studies with sleep data",
            expected_output=QueryModel(
                mentions=[
                    _m("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                    # "sleep data" is a category — no hierarchy yet, so the
                    # agent expands to multiple sleep concepts. Accept any
                    # that include Sleep Duration.
                    _m("sleep", Facet.MEASUREMENT, ["Sleep Duration"]),
                ]
            ),
        ),
        Case(
            name="negation",
            inputs="echocardiography studies but not transesophageal",
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
            name="or-data-types",
            inputs="studies with WGS or WXS data and cholesterol",
            expected_output=QueryModel(
                mentions=[
                    # "WGS or WXS" → single mention with both values (OR within)
                    _m("WGS or WXS", Facet.DATA_TYPE, ["WGS", "WXS"]),
                    _m("cholesterol", Facet.MEASUREMENT, ["Total Cholesterol"]),
                ]
            ),
        ),
        Case(
            name="study-design",
            inputs="case-control WGS studies",
            expected_output=QueryModel(
                mentions=[
                    _m("case-control", Facet.STUDY_DESIGN, ["Case-Control"]),
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                ]
            ),
        ),
        Case(
            name="consent-with-modifier",
            inputs="HMB-IRB studies with smoking data",
            expected_output=QueryModel(
                mentions=[
                    _m("HMB-IRB", Facet.CONSENT_CODE, ["HMB-IRB"]),
                    _m("smoking", Facet.MEASUREMENT, ["Smoking Status"]),
                ]
            ),
        ),
        Case(
            name="same-facet-and",
            inputs="studies with both heart disease and diabetes",
            expected_output=QueryModel(
                mentions=[
                    _m("heart disease", Facet.FOCUS, ["Cardiovascular Diseases"]),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ]
            ),
        ),
        # --- Consent code semantic resolution (full pipeline) ---
        Case(
            name="consent-semantic-general-research",
            inputs="general research use studies with BMI",
            expected_output=QueryModel(
                mentions=[
                    _m("general research use", Facet.CONSENT_CODE, ["GRU"]),
                    _m("BMI", Facet.MEASUREMENT, ["Body Mass Index"]),
                ]
            ),
        ),
        Case(
            name="consent-disease-alzheimers-typo",
            inputs=(
                "I am interested in diabetes datasets consented for use with alzhimers research"
            ),
            expected_output=QueryModel(
                mentions=[
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                    _m("alzhimers", Facet.CONSENT_CODE, ["DS-ALZ"]),
                ]
            ),
        ),
        Case(
            name="consent-breast-cancer-wgs",
            inputs="WGS datasets consented for breast cancer research",
            expected_output=QueryModel(
                mentions=[
                    _m("WGS", Facet.DATA_TYPE, ["WGS"]),
                    _m("breast cancer", Facet.CONSENT_CODE, ["DS-BRCA"]),
                ]
            ),
        ),
        # --- Multi-platform ---
        Case(
            name="anvil-and-bdc",
            inputs="datasets hosted by AnVIL and BioData Catalyst",
            expected_output=QueryModel(
                mentions=[
                    _m("AnVIL", Facet.PLATFORM, ["AnVIL"]),
                    _m("BioData Catalyst", Facet.PLATFORM, ["BDC"]),
                ]
            ),
        ),
        # --- Obscure and nonsense terms ---
        Case(
            name="exercise-with-wiffelball",
            inputs="studies measuring exercise and wiffelball",
            # "exercise" resolves to Physical Activity (28 studies).
            # "wiffelball" is misspelled but actually exists in the hierarchy
            # as "Organized Wiffleball Participation" (1 study!). The agent
            # finds this obscure concept and resolves it.
            expected_output=QueryModel(
                mentions=[
                    _m("exercise", Facet.MEASUREMENT, ["Physical Activity"]),
                    _m(
                        "wiffelball",
                        Facet.MEASUREMENT,
                        ["Organized Wiffleball Participation"],
                    ),
                ]
            ),
        ),
        Case(
            name="exercise-with-true-nonsense",
            inputs="studies measuring exercise and blorpquantz",
            # "exercise" should resolve; "blorpquantz" is a made-up word
            # with no possible match. System should resolve exercise and
            # either ignore or message about the unresolvable term.
            expected_output=QueryModel(
                mentions=[
                    _m("exercise", Facet.MEASUREMENT, ["Physical Activity"]),
                ]
            ),
        ),
        # --- Demographic facets ---
        Case(
            name="sex-female-measurement",
            inputs="studies with female participants and blood pressure data",
            # sex=Female is a small facet (resolved by extract agent directly).
            # blood pressure goes through the resolve agent.
            expected_output=QueryModel(
                mentions=[
                    _m("female", Facet.SEX, ["Female"]),
                    _m(
                        "blood pressure",
                        Facet.MEASUREMENT,
                        ["Systolic Blood Pressure"],
                    ),
                ]
            ),
        ),
        Case(
            name="race-ethnicity-platform",
            inputs="African American cohorts on BDC",
            expected_output=QueryModel(
                mentions=[
                    _m(
                        "African American",
                        Facet.RACE_ETHNICITY,
                        ["Black or African American"],
                    ),
                    _m("BDC", Facet.PLATFORM, ["BDC"]),
                ]
            ),
        ),
        Case(
            name="ancestry-focus",
            inputs="European ancestry diabetes studies",
            expected_output=QueryModel(
                mentions=[
                    _m(
                        "European ancestry",
                        Facet.COMPUTED_ANCESTRY,
                        ["European"],
                    ),
                    _m("diabetes", Facet.FOCUS, ["Diabetes Mellitus"]),
                ]
            ),
        ),
    ],
)


async def _run_task(inputs: str) -> QueryModel:
    return await run_pipeline(inputs)


async def run_evals() -> None:
    """Run the eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
