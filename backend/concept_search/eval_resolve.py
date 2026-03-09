"""Eval harness for the resolve agent in isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .consent_logic import compute_eligible_codes, resolve_disease_name
from .index import get_index
from .models import DisambiguationOption, Facet, MatchedVariable, RawMention, ResolveResult
from .resolve_agent import run_resolve


class ResolveEvaluator(Evaluator[RawMention, ResolveResult]):
    """Scores resolve agent output against expected values.

    Scoring depends on the facet:
    - **measurement**: Recall-based — expected values are "must include".
      Returning extra related concepts is acceptable (no precision penalty).
    - **focus / consentCode**: F1-based — penalizes both missing and
      spurious values.
    - Score 1.0 if expected has no values and actual is also empty.
    - When expected has matched_variables, checks recall on variable names.
    """

    def evaluate(
        self, ctx: EvaluatorContext[RawMention, ResolveResult]
    ) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        scores: dict[str, float] = {}

        # Determine facet from inputs
        is_measurement = ctx.inputs.facet == Facet.MEASUREMENT

        # Score disambiguation (when expected has disambiguation options)
        if expected is not None and expected.disambiguation:
            exp_ids = {d.concept_id.lower() for d in expected.disambiguation}
            act_ids = {d.concept_id.lower() for d in actual.disambiguation}
            if not act_ids:
                scores["resolve_score"] = 0.0
            else:
                recall = len(exp_ids & act_ids) / len(exp_ids)
                scores["resolve_score"] = round(recall, 3)
            return scores

        # Score values (concept IDs)
        if expected is None or not expected.values:
            scores["resolve_score"] = 1.0 if not actual.values else 0.0
        else:
            exp_set = {v.lower() for v in expected.values}
            act_set = {v.lower() for v in actual.values}
            if not act_set:
                scores["resolve_score"] = 0.0
            elif is_measurement:
                # Recall-only: did the agent find all expected concepts?
                # Extra related concepts are fine.
                recall = len(exp_set & act_set) / len(exp_set)
                scores["resolve_score"] = round(recall, 3)
            else:
                # F1: penalizes both missing and spurious values.
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
        # --- Direct matches (embedding finds correct concept) ---
        Case(
            name="direct-bmi",
            inputs=_mention("body mass index", Facet.MEASUREMENT),
            # Embedding hits phenx:body_mass_index directly.
            expected_output=ResolveResult(values=["phenx:body_mass_index"]),
        ),
        Case(
            name="direct-sbp",
            inputs=_mention("systolic blood pressure", Facet.MEASUREMENT),
            # Embedding returns topmed:bp_systolic and may include archetypes.
            expected_output=ResolveResult(values=["topmed:bp_systolic"]),
        ),
        # --- Lay term rewrites ---
        Case(
            name="lay-blood-sugar",
            inputs=_mention("blood sugar", Facet.MEASUREMENT),
            # "Blood sugar" clearly means blood glucose — not truly ambiguous.
            # Parent concept covers all glucose measurements via ISA closure.
            expected_output=ResolveResult(
                values=["phenx:fasting_plasma_glucose_blood_draw"]
            ),
        ),
        # --- Category expansion ---
        Case(
            name="category-sleep",
            inputs=_mention("sleep", Facet.MEASUREMENT),
            # Broad term — ISA closure from ncpi:sleep covers all descendants
            # (sleep_duration, polysomnography, sleep_architecture, etc.).
            expected_output=ResolveResult(
                values=["ncpi:sleep"]
            ),
        ),
        Case(
            name="category-cholesterol",
            inputs=_mention("cholesterol", Facet.MEASUREMENT),
            # Broad term — must include total cholesterol. Embedding results
            # may return parent concepts (topmed:hdl) or their archetypes
            # (ncpi:hdl_*); ISA closure covers the same variables either way.
            expected_output=ResolveResult(
                values=["topmed:total_cholesterol"]
            ),
        ),
        Case(
            name="disambig-glucose",
            inputs=_mention("glucose", Facet.MEASUREMENT),
            # "Glucose" spans 3 domains: nutrition (ncpi:diet), biomarker
            # (ncpi:biomarkers), diagnosis (ncpi:disease_events).
            # Agent should disambiguate with parent concept IDs.
            expected_output=ResolveResult(
                disambiguation=[
                    DisambiguationOption(
                        concept_id="phenx:fasting_plasma_glucose_blood_draw",
                        label="Blood glucose measurement",
                    ),
                    DisambiguationOption(
                        concept_id="topmed:nutrient_intake",
                        label="Dietary glucose intake",
                    ),
                ],
                values=[],
            ),
        ),
        # --- Concepts with low relevance (embedding finds related) ---
        Case(
            name="low-relevance-echocardiography",
            inputs=_mention("echocardiography", Facet.MEASUREMENT),
            # Embedding finds echo-related BP and heart rate archetypes.
            # Any echo-related concept is acceptable.
            expected_output=ResolveResult(
                values=["ncpi:heart_rate_echo_doppler_heart_rate"]
            ),
        ),
        # --- Substance use ---
        Case(
            name="synonym-smoking",
            inputs=_mention("smoking", Facet.MEASUREMENT),
            # Broad term — embedding returns many archetypes sharing parent
            # concepts. Agent should collapse to parent concept(s) since
            # ISA closure captures all descendant variables.
            expected_output=ResolveResult(
                values=[
                    "topmed:current_smoker_baseline",
                ]
            ),
        ),
        # --- Concepts now findable via embedding ---
        Case(
            name="found-vitamin-k",
            inputs=_mention("vitamin K", Facet.MEASUREMENT),
            # Embedding finds vitamin K supplement/nutrient concepts.
            expected_output=ResolveResult(
                values=["ncpi:nutrient_intake_vitamin_k"]
            ),
        ),
        Case(
            name="rewrite-heart-disease",
            inputs=_mention("heart disease", Facet.FOCUS),
            # ISA closure means "Heart Diseases" already includes all
            # subtypes; no need to also return "Cardiovascular Diseases".
            expected_output=ResolveResult(
                values=["Heart Diseases"]
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
            # ISA closure expands "Lung Neoplasms" to include subtypes
            # (Adenocarcinoma of Lung, Carcinoma Non-Small-Cell Lung, etc.)
            expected_output=ResolveResult(
                values=["Lung Neoplasms"]
            ),
        ),
        Case(
            name="focus-pancreatic-cancer",
            inputs=_mention("pancreatic cancer", Facet.FOCUS),
            # ISA closure: "Pancreatic Neoplasms" includes descendants
            # like "Carcinoma, Pancreatic Ductal".
            expected_output=ResolveResult(
                values=["Pancreatic Neoplasms"]
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
        # --- FFQ and specific food queries ---
        Case(
            name="ffq-broad",
            inputs=_mention("food frequency questionnaire", Facet.MEASUREMENT),
            # Broad query should return the FFQ parent concept.
            expected_output=ResolveResult(
                values=["topmed:food_frequency_questionnaire"]
            ),
        ),
        Case(
            name="ffq-dairy",
            inputs=_mention("dairy intake", Facet.MEASUREMENT),
            # Embedding finds dairy nutrient archetypes and ffq dairy products.
            # Either the ffq parent or the nutrient parent is acceptable.
            expected_output=ResolveResult(
                values=["ncpi:ffq_dairy_products"]
            ),
        ),
        Case(
            name="ffq-fish",
            inputs=_mention("fish and seafood consumption", Facet.MEASUREMENT),
            # Embedding directly finds ffq_fish_seafood.
            expected_output=ResolveResult(
                values=["ncpi:ffq_fish_seafood"]
            ),
        ),
        Case(
            name="ffq-chocolate",
            inputs=_mention("chocolate consumption", Facet.MEASUREMENT),
            # Embedding finds chocolate candy archetype directly.
            expected_output=ResolveResult(
                values=["ncpi:ffq_sweets_desserts_chocolate_candy"],
            ),
        ),
        Case(
            name="broad-bp",
            inputs=_mention("blood pressure", Facet.MEASUREMENT),
            # Broad term — should include both systolic and diastolic siblings.
            expected_output=ResolveResult(
                values=["topmed:bp_systolic", "topmed:bp_diastolic"]
            ),
        ),
        # --- Embedding search: direct return vs drill-down ---
        Case(
            name="embed-direct-egfr",
            inputs=_mention("eGFR", Facet.MEASUREMENT),
            # Embedding returns archetype ncpi:kidney_function_egfr at rank 1
            # (sim=0.936). Should return directly — no drill-down needed.
            expected_output=ResolveResult(
                values=["ncpi:kidney_function_egfr"]
            ),
        ),
        Case(
            name="embed-drilldown-lung-function",
            inputs=_mention("lung function", Facet.MEASUREMENT),
            # Embedding returns ncpi:respiratory at top. The child
            # topmed:pulmonary_function_detailed is redundant under
            # ISA closure — respiratory covers all descendants.
            expected_output=ResolveResult(
                values=["ncpi:respiratory"]
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
    # Eagerly load the embedding model before parallel eval runs
    # to avoid concurrent model initialization (PyTorch meta tensor bug).
    from .embeddings import get_model

    get_model()
    report = await dataset.evaluate(_run_task)
    report.print()


def main() -> None:
    """CLI entry point for running resolve evals."""
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
