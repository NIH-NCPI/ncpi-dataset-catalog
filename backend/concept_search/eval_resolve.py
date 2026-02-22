"""Eval harness for the resolve agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .index import get_index
from .models import Facet, RawMention, ResolveResult
from .resolve_agent import run_resolve


class ResolveEvaluator(Evaluator[RawMention, ResolveResult]):
    """Scores resolve agent output using recall on expected values.

    Matching logic:
    - Values are compared case-insensitively.
    - Recall: all expected values must appear in actual.
    - Extra values in actual are not penalized.
    - Score 1.0 if expected has no values (just checks agent returns something).
    """

    def evaluate(
        self, ctx: EvaluatorContext[RawMention, ResolveResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None or not expected.values:
            # If we expect empty, score 1.0 if actual is also empty
            return {
                "resolve_score": 1.0 if not actual.values else 0.0
            }

        exp_set = {v.lower() for v in expected.values}
        act_set = {v.lower() for v in actual.values}
        if not act_set:
            return {"resolve_score": 0.0}
        hits = exp_set & act_set
        return {"resolve_score": round(len(hits) / len(exp_set), 3)}


def _mention(text: str, facet: Facet) -> RawMention:
    """Build a raw mention input for the resolve agent."""
    return RawMention(facet=facet, text=text, values=[])


dataset = Dataset[RawMention, ResolveResult, ResolveResult](
    evaluators=[ResolveEvaluator()],
    cases=[
        # --- Direct matches ---
        Case(
            name="direct-bmi",
            inputs=_mention("body mass index", Facet.MEASUREMENT),
            expected_output=ResolveResult(values=["Body Mass Index"]),
        ),
        Case(
            name="direct-sbp",
            inputs=_mention("systolic blood pressure", Facet.MEASUREMENT),
            expected_output=ResolveResult(values=["Systolic Blood Pressure"]),
        ),
        Case(
            name="direct-diabetes-focus",
            inputs=_mention("diabetes", Facet.FOCUS),
            expected_output=ResolveResult(values=["Diabetes Mellitus"]),
        ),
        Case(
            name="direct-consent-gru",
            inputs=_mention("GRU", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["GRU"]),
        ),
        # --- Lay term rewrites ---
        Case(
            name="lay-blood-sugar",
            inputs=_mention("blood sugar", Facet.MEASUREMENT),
            # Agent should search "blood sugar", find low-count results,
            # then rewrite to "glucose" and find Fasting Glucose (44 studies).
            expected_output=ResolveResult(values=["Fasting Glucose"]),
        ),
        Case(
            name="lay-blood-pressure",
            inputs=_mention("blood pressure", Facet.MEASUREMENT),
            expected_output=ResolveResult(
                values=["Systolic Blood Pressure"]
            ),
        ),
        # --- Category expansion ---
        Case(
            name="category-sleep",
            inputs=_mention("sleep", Facet.MEASUREMENT),
            # "sleep" is broad — agent should return multiple sleep concepts.
            # Accept any result that includes Sleep Duration.
            expected_output=ResolveResult(values=["Sleep Duration"]),
        ),
        Case(
            name="category-cholesterol",
            inputs=_mention("cholesterol", Facet.MEASUREMENT),
            # "cholesterol" is ambiguous — Total, HDL, LDL, Dietary, etc.
            # Agent should return broad match and disambiguate via message.
            expected_output=ResolveResult(values=["Total Cholesterol"]),
        ),
        Case(
            name="disambig-glucose",
            inputs=_mention("glucose", Facet.MEASUREMENT),
            # "glucose" spans 5 categories: Endocrine (Fasting Glucose, 44),
            # Lab Tests (Glucose, 38), Dietary (Glucose Intake, 5), etc.
            # Agent should pick Fasting Glucose (highest count) and
            # disambiguate — importantly NOT an example in the prompt.
            expected_output=ResolveResult(values=["Fasting Glucose"]),
        ),
        # --- Medical synonym ---
        Case(
            name="synonym-echocardiography",
            inputs=_mention("echocardiography", Facet.MEASUREMENT),
            expected_output=ResolveResult(values=["Echocardiography"]),
        ),
        Case(
            name="synonym-smoking",
            inputs=_mention("smoking", Facet.MEASUREMENT),
            expected_output=ResolveResult(values=["Smoking Status"]),
        ),
        # --- Harder rewrites ---
        Case(
            name="rewrite-vitamin-k",
            inputs=_mention("vitamin K", Facet.MEASUREMENT),
            expected_output=ResolveResult(values=["Vitamin K Intake"]),
        ),
        Case(
            name="rewrite-heart-disease",
            inputs=_mention("heart disease", Facet.FOCUS),
            # With category drill-down, agent sees full list and picks
            # the broader "Cardiovascular Diseases" (81 studies) over
            # "Heart Diseases" (4 studies). Both are valid.
            expected_output=ResolveResult(values=["Cardiovascular Diseases"]),
        ),
        # --- Focus/disease via category drill-down ---
        Case(
            name="focus-cancer",
            inputs=_mention("cancer", Facet.FOCUS),
            expected_output=ResolveResult(values=["Neoplasms"]),
        ),
        Case(
            name="focus-breast-cancer",
            inputs=_mention("breast cancer", Facet.FOCUS),
            expected_output=ResolveResult(values=["Breast Neoplasms"]),
        ),
        Case(
            name="focus-lung-cancer",
            inputs=_mention("lung cancer", Facet.FOCUS),
            expected_output=ResolveResult(values=["Lung Neoplasms"]),
        ),
        Case(
            name="focus-diabetes",
            inputs=_mention("diabetes", Facet.FOCUS),
            expected_output=ResolveResult(values=["Diabetes Mellitus"]),
        ),
        Case(
            name="focus-type-2-diabetes",
            inputs=_mention("type 2 diabetes", Facet.FOCUS),
            expected_output=ResolveResult(values=["Diabetes Mellitus, Type 2"]),
        ),
        Case(
            name="focus-asthma",
            inputs=_mention("asthma", Facet.FOCUS),
            expected_output=ResolveResult(values=["Asthma"]),
        ),
        Case(
            name="focus-als",
            inputs=_mention("ALS", Facet.FOCUS),
            expected_output=ResolveResult(values=["Amyotrophic Lateral Sclerosis"]),
        ),
        Case(
            name="focus-parkinsons",
            inputs=_mention("Parkinson's disease", Facet.FOCUS),
            expected_output=ResolveResult(values=["Parkinson Disease"]),
        ),
        Case(
            name="focus-sickle-cell",
            inputs=_mention("sickle cell disease", Facet.FOCUS),
            expected_output=ResolveResult(values=["Anemia, Sickle Cell"]),
        ),
        Case(
            name="focus-copd",
            inputs=_mention("COPD", Facet.FOCUS),
            expected_output=ResolveResult(
                values=["Pulmonary Disease, Chronic Obstructive"]
            ),
        ),
        Case(
            name="focus-covid",
            inputs=_mention("COVID-19", Facet.FOCUS),
            expected_output=ResolveResult(values=["COVID-19"]),
        ),
        Case(
            name="focus-lay-heart-attack",
            inputs=_mention("heart attack", Facet.FOCUS),
            expected_output=ResolveResult(values=["Myocardial Infarction"]),
        ),
        Case(
            name="focus-rheumatoid-arthritis",
            inputs=_mention("rheumatoid arthritis", Facet.FOCUS),
            expected_output=ResolveResult(values=["Arthritis, Rheumatoid"]),
        ),
        Case(
            name="focus-schizophrenia",
            inputs=_mention("schizophrenia", Facet.FOCUS),
            expected_output=ResolveResult(values=["Schizophrenia"]),
        ),
        # --- Consent code semantic resolution ---
        Case(
            name="consent-gru-direct",
            inputs=_mention("GRU", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["GRU"]),
        ),
        Case(
            name="consent-general-research",
            inputs=_mention("general research use", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["GRU"]),
        ),
        Case(
            name="consent-hmb-direct",
            inputs=_mention("HMB", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["HMB"]),
        ),
        Case(
            name="consent-health-medical",
            inputs=_mention("health medical biomedical", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["HMB"]),
        ),
        Case(
            name="consent-disease-specific-cvd",
            inputs=_mention("cardiovascular disease specific", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["DS-CVD"]),
        ),
        Case(
            name="consent-breast-cancer",
            inputs=_mention("breast cancer research", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["DS-BRCA"]),
        ),
        Case(
            name="consent-not-for-profit",
            inputs=_mention("general research, not for profit", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["GRU-NPU"]),
        ),
        Case(
            name="consent-hmb-irb",
            inputs=_mention("HMB-IRB", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["HMB-IRB"]),
        ),
        Case(
            name="consent-diabetes",
            inputs=_mention("diabetes research", Facet.CONSENT_CODE),
            # Eligibility: should return DS-DIAB-* codes (via compute_consent_eligibility)
            expected_output=ResolveResult(values=["DS-DIAB-NPU"]),
        ),
        # --- Consent eligibility resolution ---
        Case(
            name="consent-for-profit-cancer",
            inputs=_mention("for-profit cancer", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["DS-CA"]),
        ),
        Case(
            name="consent-explicit-gru",
            inputs=_mention("GRU", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["GRU", "GRU-IRB"]),
        ),
        Case(
            name="consent-explicit-hmb",
            inputs=_mention("HMB", Facet.CONSENT_CODE),
            expected_output=ResolveResult(values=["HMB", "HMB-IRB"]),
        ),
        Case(
            name="consent-sub-disease",
            inputs=_mention("type 1 diabetes research consent", Facet.CONSENT_CODE),
            # DS-T1D-IRB exists in the index
            expected_output=ResolveResult(values=["DS-T1D-IRB"]),
        ),
        Case(
            name="consent-consented-diabetes",
            inputs=_mention("diabetes", Facet.CONSENT_CODE),
            # Should include GRU (always eligible) and HMB (health/disease)
            # plus DS-DIAB family — recall scoring checks all are present
            expected_output=ResolveResult(
                values=["GRU", "HMB", "DS-DIAB-NPU"]
            ),
        ),
        Case(
            name="consent-consented-alzheimers",
            inputs=_mention("Alzheimer's", Facet.CONSENT_CODE),
            # GRU always eligible, HMB for disease research
            expected_output=ResolveResult(values=["GRU", "HMB"]),
        ),
        Case(
            name="consent-disease-only-diabetes",
            inputs=_mention("diabetes only", Facet.CONSENT_CODE),
            # "only" → disease_only=True, should return DS-DIAB* but NOT GRU/HMB
            expected_output=ResolveResult(values=["DS-DIAB-NPU"]),
        ),
        Case(
            name="consent-disease-only-cancer",
            inputs=_mention("specifically cancer", Facet.CONSENT_CODE),
            # "specifically" → disease_only=True
            expected_output=ResolveResult(values=["DS-CA"]),
        ),
        # --- GRU vs HMB disambiguation ---
        Case(
            name="consent-social-science",
            inputs=_mention("social science behavioral genetics research", Facet.CONSENT_CODE),
            # NOT health/medical → general purpose → GRU only
            # HMB is restricted to health/medical/biomedical
            expected_output=ResolveResult(values=["GRU"]),
        ),
        Case(
            name="consent-biomedical",
            inputs=_mention("biomedical research on aging", Facet.CONSENT_CODE),
            # Explicitly biomedical → health purpose → GRU + HMB
            expected_output=ResolveResult(values=["GRU", "HMB"]),
        ),
        Case(
            name="consent-for-profit-health",
            inputs=_mention("for-profit biomedical health research", Facet.CONSENT_CODE),
            # Health purpose + for-profit → GRU + HMB minus NPU variants
            expected_output=ResolveResult(values=["GRU", "HMB"]),
        ),
        Case(
            name="consent-population-genetics",
            inputs=_mention("population genetics, not disease-related", Facet.CONSENT_CODE),
            # Explicitly not disease/health → general → GRU only
            expected_output=ResolveResult(values=["GRU"]),
        ),
    ],
)


async def _run_task(inputs: RawMention) -> ResolveResult:
    index = get_index()
    return await run_resolve(inputs, index)


async def run_evals() -> None:
    """Run the resolve eval dataset and print the report."""
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running resolve evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
