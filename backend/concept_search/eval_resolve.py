"""Eval harness for the resolve agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import get_index
from .models import Facet, MatchedVariable, RawMention, ResolveResult
from .resolve_agent import run_resolve


class ResolveEvaluator(Evaluator[RawMention, ResolveResult]):
    """Scores resolve agent output using F1 on expected values.

    Matching logic:
    - Values are compared case-insensitively.
    - F1: harmonic mean of precision and recall. Penalizes both
      missing expected values and spurious extra values.
    - Score 1.0 if expected has no values and actual is also empty.
    - When expected has matched_variables, checks that the agent
      returned at least those variable names (recall-based).
    """

    def evaluate(
        self, ctx: EvaluatorContext[RawMention, ResolveResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        scores: dict[str, float] = {}

        # Score values (concept IDs)
        if expected is None or not expected.values:
            scores["resolve_score"] = 1.0 if not actual.values else 0.0
        else:
            exp_set = {v.lower() for v in expected.values}
            act_set = {v.lower() for v in actual.values}
            if not act_set:
                scores["resolve_score"] = 0.0
            else:
                hits = len(exp_set & act_set)
                precision = hits / len(act_set)
                recall = hits / len(exp_set)
                if precision + recall == 0:
                    scores["resolve_score"] = 0.0
                else:
                    f1 = 2 * precision * recall / (precision + recall)
                    scores["resolve_score"] = round(f1, 3)

        # Score matched_variables (recall: did the agent find the expected vars?)
        if expected is not None and expected.matched_variables:
            exp_vars = {v.variable_name.lower() for v in expected.matched_variables}
            act_vars = {v.variable_name.lower() for v in actual.matched_variables}
            if not act_vars:
                scores["variables_score"] = 0.0
            else:
                recall = len(exp_vars & act_vars) / len(exp_vars)
                scores["variables_score"] = round(recall, 3)

        return scores


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
        # --- Direct matches (tree walk finds correct concept) ---
        Case(
            name="direct-bmi",
            inputs=_mention("body mass index", Facet.MEASUREMENT),
            # Walk: anthropometry → phenx:body_mass_index
            expected_output=ResolveResult(values=["phenx:body_mass_index"]),
        ),
        Case(
            name="direct-sbp",
            inputs=_mention("systolic blood pressure", Facet.MEASUREMENT),
            # Walk: biomarkers → topmed:bp_systolic
            expected_output=ResolveResult(values=["topmed:bp_systolic"]),
        ),
        # --- Lay term rewrites ---
        Case(
            name="lay-blood-sugar",
            inputs=_mention("blood sugar", Facet.MEASUREMENT),
            # Walk: biomarkers → fasting glucose concept (lay→clinical mapping)
            expected_output=ResolveResult(
                values=["phenx:fasting_plasma_glucose_blood_draw"]
            ),
        ),
        Case(
            name="lay-blood-pressure",
            inputs=_mention("blood pressure", Facet.MEASUREMENT),
            # Walk: biomarkers → both systolic + diastolic
            expected_output=ResolveResult(
                values=["topmed:bp_diastolic", "topmed:bp_systolic"]
            ),
        ),
        # --- Category expansion ---
        Case(
            name="category-sleep",
            inputs=_mention("sleep", Facet.MEASUREMENT),
            # "sleep" maps directly to ncpi:sleep top-level category.
            # ISA closure includes all children (sleep_duration, sleep_apnea).
            expected_output=ResolveResult(values=["ncpi:sleep"]),
        ),
        Case(
            name="category-cholesterol",
            inputs=_mention("cholesterol", Facet.MEASUREMENT),
            # Walk: biomarkers → HDL, LDL, total cholesterol.
            # Triglycerides are a separate lipid, may or may not be included.
            expected_output=ResolveResult(
                values=[
                    "topmed:hdl",
                    "topmed:ldl",
                    "topmed:total_cholesterol",
                ]
            ),
        ),
        Case(
            name="disambig-glucose",
            inputs=_mention("glucose", Facet.MEASUREMENT),
            # Walk: biomarkers → fasting plasma glucose is the primary match.
            expected_output=ResolveResult(
                values=["phenx:fasting_plasma_glucose_blood_draw"]
            ),
        ),
        # --- Concepts not in catalog (agent should report gracefully) ---
        Case(
            name="no-match-echocardiography",
            inputs=_mention("echocardiography", Facet.MEASUREMENT),
            # No echocardiography concept exists; agent returns empty with message.
            expected_output=ResolveResult(values=[]),
        ),
        # --- Substance use ---
        Case(
            name="synonym-smoking",
            inputs=_mention("smoking", Facet.MEASUREMENT),
            # Walk: substance_use → returns tobacco/smoking-related concepts.
            # "smoking" is broad, so agent returns multiple tobacco concepts.
            # Must include the main smoking status concept; may include others.
            expected_output=ResolveResult(
                values=[
                    "phenx:amount_type_and_frequency_of_recent_cigarette_use",
                    "phenx:protocol_2_tobacco_30day_quantity_and_frequency_adult_protocol",
                    "phenx:protocol_2_tobacco_age_of_initiation_of_use_adult_protocol",
                    "phenx:protocol_2_tobacco_age_of_offset_of_use_adult_protocol",
                    "phenx:protocol_2_tobacco_smoking_status_adult_protocol",
                    "phenx:substance_abuse_and_dependence_past_year_tobacco",
                    "phenx:tobacco_nicotine_dependence",
                    "phenx:tobacco_noncigarette_product_use",
                    "phenx:use_of_tobacco_products",
                ]
            ),
        ),
        # --- Concepts not in catalog ---
        Case(
            name="no-match-vitamin-k",
            inputs=_mention("vitamin K", Facet.MEASUREMENT),
            # No vitamin K specific concept; agent returns empty with message.
            expected_output=ResolveResult(values=[]),
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
        # --- Tree-walk drill-down (concept hierarchy navigation) ---
        Case(
            name="walk-ffq-broad",
            inputs=_mention("food frequency questionnaire", Facet.MEASUREMENT),
            # Broad query should stop at the FFQ concept, not drill deeper.
            expected_output=ResolveResult(
                values=["topmed:food_frequency_questionnaire"]
            ),
        ),
        Case(
            name="walk-ffq-dairy",
            inputs=_mention("dairy intake", Facet.MEASUREMENT),
            # Should walk: diet → FFQ → ffq_dairy_products
            expected_output=ResolveResult(
                values=["ncpi:ffq_dairy_products"]
            ),
        ),
        Case(
            name="walk-ffq-fish",
            inputs=_mention("fish and seafood consumption", Facet.MEASUREMENT),
            # Should walk: diet → FFQ → ffq_fish_seafood
            expected_output=ResolveResult(
                values=["ncpi:ffq_fish_seafood"]
            ),
        ),
        Case(
            name="walk-ffq-leaf-with-variables",
            inputs=_mention("chocolate consumption", Facet.MEASUREMENT),
            # Should walk to ffq_sweets_desserts and return matching variables.
            expected_output=ResolveResult(
                values=["ncpi:ffq_sweets_desserts"],
                matched_variables=[
                    MatchedVariable(variable_name="CHOC", description="FFQ: CHOCOLATE"),
                    MatchedVariable(variable_name="FFD118", description="CHOCOLATE"),
                ],
            ),
        ),
        Case(
            name="walk-bp",
            inputs=_mention("blood pressure", Facet.MEASUREMENT),
            # Should walk: biomarkers → find bp_systolic + bp_diastolic
            expected_output=ResolveResult(
                values=["topmed:bp_systolic", "topmed:bp_diastolic"]
            ),
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
