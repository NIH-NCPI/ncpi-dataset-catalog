"""Eval harness for the resolve agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import get_index
from .models import Facet, RawMention, ResolveResult
from .resolve_agent import run_resolve


class ResolveEvaluator(Evaluator[RawMention, ResolveResult]):
    """Scores resolve agent output using F1 on expected values.

    Matching logic:
    - Values are compared case-insensitively.
    - F1: harmonic mean of precision and recall. Penalizes both
      missing expected values and spurious extra values.
    - Score 1.0 if expected has no values and actual is also empty.
    """

    def evaluate(
        self, ctx: EvaluatorContext[RawMention, ResolveResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None or not expected.values:
            return {
                "resolve_score": 1.0 if not actual.values else 0.0
            }

        exp_set = {v.lower() for v in expected.values}
        act_set = {v.lower() for v in actual.values}
        if not act_set:
            return {"resolve_score": 0.0}
        hits = len(exp_set & act_set)
        precision = hits / len(act_set)
        recall = hits / len(exp_set)
        if precision + recall == 0:
            return {"resolve_score": 0.0}
        f1 = 2 * precision * recall / (precision + recall)
        return {"resolve_score": round(f1, 3)}


def _mention(text: str, facet: Facet) -> RawMention:
    """Build a raw mention input for the resolve agent."""
    return RawMention(facet=facet, text=text, values=[])


# ---------------------------------------------------------------------------
# Dynamic consent code expectations
# ---------------------------------------------------------------------------

def _consent_expected(**kwargs: object) -> ResolveResult:
    """Compute expected consent code values deterministically.

    Loads the index once, gets all consent codes, and calls
    ``compute_eligible_codes`` with the given kwargs.  This keeps
    expectations in sync with the actual catalog data.

    Args:
        **kwargs: Forwarded to ``compute_eligible_codes`` (after resolving
            any ``disease`` name to an abbreviation).

    Returns:
        A :class:`ResolveResult` with sorted eligible codes.
    """
    index = get_index()
    all_codes = [m.value for m in index.list_facet_values("consentCode")]
    # Resolve disease name if provided
    if "disease" in kwargs:
        kwargs["disease"] = resolve_disease_name(str(kwargs["disease"]))
    eligible = compute_eligible_codes(all_codes, **kwargs)  # type: ignore[arg-type]
    return ResolveResult(values=sorted(eligible))


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
        # (diabetes/focus is tested as focus-diabetes below)
        # (GRU direct match is tested as consent-gru-direct below)
        # --- Lay term rewrites ---
        Case(
            name="lay-blood-sugar",
            inputs=_mention("blood sugar", Facet.MEASUREMENT),
            # Agent should search "blood sugar", find low-count results,
            # then rewrite to "glucose" and find glucose-related concepts.
            expected_output=ResolveResult(
                values=["Blood Glucose", "Fasting Glucose", "Glucose", "Serum Glucose"]
            ),
        ),
        Case(
            name="lay-blood-pressure",
            inputs=_mention("blood pressure", Facet.MEASUREMENT),
            expected_output=ResolveResult(
                values=["Diastolic Blood Pressure", "Systolic Blood Pressure"]
            ),
        ),
        # --- Category expansion ---
        Case(
            name="category-sleep",
            inputs=_mention("sleep", Facet.MEASUREMENT),
            # "sleep" is broad — agent should return multiple sleep concepts.
            expected_output=ResolveResult(
                values=[
                    "Daytime Sleepiness",
                    "Epworth Sleepiness Scale",
                    "Excessive Daytime Sleepiness",
                    "Obstructive Sleep Apnea History",
                    "Oxygen Therapy Use During Sleep",
                    "Sleep Apnea History",
                    "Sleep Disorder History",
                    "Sleep Disturbance",
                    "Sleep Duration",
                    "Sleep Efficiency",
                    "Sleep Latency",
                    "Sleep Maintenance Insomnia",
                    "Sleep Medication Use",
                    "Sleep Onset Difficulty",
                    "Sleep Onset Insomnia",
                    "Sleep Onset Latency",
                    "Sleep Problems",
                    "Sleep Quality",
                    "Total Sleep Time",
                    "Wake After Sleep Onset",
                ]
            ),
        ),
        Case(
            name="category-cholesterol",
            inputs=_mention("cholesterol", Facet.MEASUREMENT),
            # "cholesterol" is ambiguous — Total, HDL, LDL, Triglycerides.
            # Agent should return broad match and disambiguate via message.
            expected_output=ResolveResult(
                values=["HDL Cholesterol", "LDL Cholesterol", "Total Cholesterol", "Triglycerides"]
            ),
        ),
        Case(
            name="disambig-glucose",
            inputs=_mention("glucose", Facet.MEASUREMENT),
            # "glucose" spans multiple categories — agent should return
            # the main glucose-related measurement concepts.
            expected_output=ResolveResult(
                values=[
                    "2-Hour Plasma Glucose",
                    "Fasting Blood Glucose",
                    "Fasting Glucose",
                    "Postprandial Blood Glucose",
                ]
            ),
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
            expected_output=ResolveResult(
                values=["Current Smoking Status", "Smoking History", "Smoking Status"]
            ),
        ),
        # --- Harder rewrites ---
        Case(
            name="rewrite-vitamin-k",
            inputs=_mention("vitamin K", Facet.MEASUREMENT),
            expected_output=ResolveResult(
                values=["Vitamin K Intake", "Vitamin K Supplementation"]
            ),
        ),
        Case(
            name="rewrite-heart-disease",
            inputs=_mention("heart disease", Facet.FOCUS),
            # With category drill-down, agent sees full list and picks
            # both broad and specific heart disease terms.
            expected_output=ResolveResult(
                values=["Cardiovascular Diseases", "Heart Diseases"]
            ),
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
            expected_output=ResolveResult(
                values=[
                    "Adenocarcinoma of Lung",
                    "Carcinoma, Non-Small-Cell Lung",
                    "Lung Neoplasms",
                    "Small Cell Lung Carcinoma",
                ]
            ),
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
        # --- Consent code semantic resolution (dynamic expectations) ---
        Case(
            name="consent-gru-direct",
            inputs=_mention("GRU", Facet.CONSENT_CODE),
            expected_output=_consent_expected(explicit_code="GRU"),
        ),
        Case(
            name="consent-general-research",
            inputs=_mention("general research use", Facet.CONSENT_CODE),
            expected_output=_consent_expected(explicit_code="GRU"),
        ),
        Case(
            name="consent-hmb-direct",
            inputs=_mention("HMB", Facet.CONSENT_CODE),
            expected_output=_consent_expected(explicit_code="HMB"),
        ),
        Case(
            name="consent-health-medical",
            inputs=_mention("health medical biomedical", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="health"),
        ),
        Case(
            name="consent-disease-specific-cvd",
            inputs=_mention("cardiovascular disease specific", Facet.CONSENT_CODE),
            expected_output=_consent_expected(explicit_code="DS-CVD"),
        ),
        Case(
            name="consent-breast-cancer",
            inputs=_mention("breast cancer research", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="BRCA"),
        ),
        Case(
            name="consent-not-for-profit",
            inputs=_mention("general research, not for profit", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="general"),
        ),
        Case(
            name="consent-hmb-irb",
            inputs=_mention("HMB-IRB", Facet.CONSENT_CODE),
            expected_output=_consent_expected(explicit_code="HMB-IRB"),
        ),
        Case(
            name="consent-diabetes",
            inputs=_mention("diabetes research", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="DIAB"),
        ),
        # --- Consent eligibility resolution ---
        Case(
            name="consent-for-profit-cancer",
            inputs=_mention("for-profit cancer", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="CA", is_nonprofit=False),
        ),
        Case(
            name="consent-sub-disease",
            inputs=_mention("type 1 diabetes research consent", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="T1D"),
        ),
        Case(
            name="consent-consented-diabetes",
            inputs=_mention("diabetes", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="DIAB"),
        ),
        Case(
            name="consent-consented-alzheimers",
            inputs=_mention("Alzheimer's", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="health"),
        ),
        Case(
            name="consent-disease-only-diabetes",
            inputs=_mention("diabetes only", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="DIAB", disease_only=True),
        ),
        Case(
            name="consent-disease-only-cancer",
            inputs=_mention("specifically cancer", Facet.CONSENT_CODE),
            expected_output=_consent_expected(purpose="disease", disease="CA", disease_only=True),
        ),
        # --- GRU vs HMB disambiguation ---
        Case(
            name="consent-social-science",
            inputs=_mention("social science behavioral genetics research", Facet.CONSENT_CODE),
            # NOT health/medical -> general purpose -> GRU only
            # HMB is restricted to health/medical/biomedical
            expected_output=_consent_expected(purpose="general"),
        ),
        Case(
            name="consent-biomedical",
            inputs=_mention("biomedical research on aging", Facet.CONSENT_CODE),
            # Explicitly biomedical -> health purpose -> GRU + HMB
            expected_output=_consent_expected(purpose="health"),
        ),
        Case(
            name="consent-for-profit-health",
            inputs=_mention("for-profit biomedical health research", Facet.CONSENT_CODE),
            # Health purpose + for-profit -> GRU + HMB minus NPU variants
            expected_output=_consent_expected(purpose="health", is_nonprofit=False),
        ),
        Case(
            name="consent-population-genetics",
            inputs=_mention("population genetics, not disease-related", Facet.CONSENT_CODE),
            # Explicitly not disease/health -> general -> GRU only
            expected_output=_consent_expected(purpose="general"),
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
