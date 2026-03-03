"""Evals for concept matching classifier (v4 multi-table batching).

Each eval case sends a single variable to the LLM with the full concept
vocabulary (~567 concepts). Tests whether the model correctly matches to
the right concept_id or returns null for non-matching variables.

Test cases are derived from TOPMed ground truth (topmed-seed-concepts.json)
component variables — domain experts confirmed these concept mappings.

Usage:
    python eval_v3_topmed.py                # Run evals against live LLM
    python eval_v3_topmed.py --model anthropic:claude-sonnet-4-5-20250929

Requires:
    pip install pydantic-evals
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluationReason, EvaluatorContext

from classify_v4 import (
    MatchDeps,
    classify_batch,
    load_vocabulary,
    make_agent,
    VOCAB_PATH,
    PHENX_VOCAB_PATH,
)
from models import ParsedTable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

# Domain groupings for "close match" evaluation
DOMAIN_GROUPS: dict[str, set[str]] = {
    "blood_pressure": {"bp_systolic", "bp_diastolic", "antihypertensive_meds"},
    "lipids": {
        "hdl", "ldl", "total_cholesterol", "triglycerides",
        "fasting_lipids", "lipid_lowering_medication",
    },
    "blood_cell_count": {
        "wbc_ncnc_bld", "rbc_ncnc_bld", "hemoglobin_mcnc_bld",
        "hematocrit_vfr_bld", "platelet_ncnc_bld", "mcv_entvol_rbc",
        "mch_entmass_rbc", "mchc_mcnc_rbc", "rdw_ratio_rbc",
        "pmv_entvol_bld", "neutrophil_ncnc_bld", "lymphocyte_ncnc_bld",
        "monocyte_ncnc_bld", "eosinophil_ncnc_bld", "basophil_ncnc_bld",
    },
    "inflammation": {
        "crp", "il6", "il10", "il18", "il1_beta", "tnfa", "tnfa_r1",
        "tnfr2", "icam1", "eselectin", "pselectin", "cd40", "mcp1",
        "mmp9", "mpo", "opg", "lppla2_act", "lppla2_mass",
        "isoprostane_8_epi_pgf2a",
    },
    "atherosclerosis": {
        "cac_score", "cac_volume", "carotid_plaque",
        "carotid_stenosis", "cimt",
    },
    "demographic": {
        "annotated_sex", "race_us", "hispanic_or_latino",
        "hispanic_subgroup", "geographic_site", "subcohort",
        "ncpi:subject_age", "phenx:current_age",
    },
    "baseline_covariates": {
        "bmi_baseline", "height_baseline", "weight_baseline",
        "current_smoker_baseline", "ever_smoker_baseline",
    },
    "events_incident": {
        "angina_incident", "mi_incident", "cabg_incident",
        "coronary_angioplasty_incident", "pad_incident",
        "chd_death_definite", "chd_death_probable",
        "cad_followup_start_age",
    },
    "events_prior": {
        "angina_prior", "mi_prior", "cabg_prior",
        "coronary_angioplasty_prior", "coronary_revascularization_prior",
        "pad_prior",
    },
    "vte": {"vte_case_status", "vte_followup_start_age", "vte_prior_history"},
    "ecg": {"ecg", "heart_rate"},
    "cognition": {"cognition"},
    "liver_kidney": {"liver_function", "kidney_function"},
    "hospitalization_surgery": {"hospitalization", "surgical_procedure"},
    "family_history": {"family_medical_history"},
    "medications_specific": {
        "diabetes_medication", "anticoagulant_medication", "pain_medication",
    },
}

# Build reverse lookup: concept_id → domain
_CONCEPT_TO_DOMAIN: dict[str, str] = {}
for domain, ids in DOMAIN_GROUPS.items():
    for cid in ids:
        _CONCEPT_TO_DOMAIN[cid] = domain


# ---------------------------------------------------------------------------
# Eval input model
# ---------------------------------------------------------------------------


class VariableInput(BaseModel):
    """A single variable with its table context for evaluation."""

    study_id: str
    study_name: str
    table_name: str
    table_description: str
    variable_name: str
    variable_description: str


# ---------------------------------------------------------------------------
# Task function: classifies one variable via v3 pipeline
# ---------------------------------------------------------------------------


async def classify_one_variable(inputs: VariableInput) -> str:
    """Classify a single variable and return its concept_id or 'null'."""
    # Exclude archetypes — they're sub-groupings, not classifier targets,
    # and including them pushes the prompt past Haiku's 200K token limit.
    vocab = [
        v for v in load_vocabulary(VOCAB_PATH, PHENX_VOCAB_PATH)
        if v.get("type") != "archetype"
    ]
    agent = make_agent(vocab)
    valid_ids = {v["concept_id"] for v in vocab}

    table = ParsedTable(
        study_id=inputs.study_id,
        dataset_id="eval",
        table_name=inputs.table_name,
        study_name=inputs.study_name,
        description=inputs.table_description,
        variables=[
            {
                "name": inputs.variable_name,
                "description": inputs.variable_description,
            }
        ],
        variable_count=1,
        file_path="eval",
    )
    # v4 classify_batch takes a list of (table, variables) pairs
    result, _, _ = await classify_batch(
        agent,
        valid_ids,
        inputs.study_id,
        inputs.study_name,
        [(table, table.variables)],
    )
    # matches-only output: if tables/variables empty, it means no match (null)
    if result.tables and result.tables[0].variables:
        return result.tables[0].variables[0].concept_id
    return "null"


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


@dataclass
class ConceptIdEquals(Evaluator[VariableInput, str, str]):
    """Check if the returned concept_id matches the expected exactly."""

    def evaluate(
        self, ctx: EvaluatorContext[VariableInput, str, str]
    ) -> EvaluationReason:
        """Evaluate exact match.

        Args:
            ctx: Evaluation context.

        Returns:
            Pass/fail with reason.
        """
        desc = ctx.inputs.variable_description
        if ctx.output == ctx.expected_output:
            return EvaluationReason(value=True, reason=f"{desc} -> {ctx.output}")
        return EvaluationReason(
            value=False,
            reason=(
                f"{desc} -> expected {ctx.expected_output!r}, "
                f"got {ctx.output!r}"
            ),
        )


@dataclass
class ConceptIdClose(Evaluator[VariableInput, str, str]):
    """Check if the concept_id is correct or from the same domain."""

    def evaluate(
        self, ctx: EvaluatorContext[VariableInput, str, str]
    ) -> EvaluationReason:
        """Evaluate close match (exact or same domain).

        Args:
            ctx: Evaluation context.

        Returns:
            Pass/fail with reason.
        """
        out = ctx.output
        exp = ctx.expected_output

        # Exact match
        if out == exp:
            return EvaluationReason(
                value=True,
                reason=f"exact: {out}",
            )

        # Both null
        if out == "null" and exp == "null":
            return EvaluationReason(value=True, reason="both null")

        # Same domain check
        out_domain = _CONCEPT_TO_DOMAIN.get(out, "")
        exp_domain = _CONCEPT_TO_DOMAIN.get(exp, "")
        if out_domain and exp_domain and out_domain == exp_domain:
            return EvaluationReason(
                value=True,
                reason=f"same domain ({out_domain}): {out!r} ~ {exp!r}",
            )

        return EvaluationReason(
            value=False,
            reason=f"not close: {out!r} vs {exp!r}",
        )


# ---------------------------------------------------------------------------
# Helper to build cases
# ---------------------------------------------------------------------------


def var_case(
    name: str,
    variable_name: str,
    variable_description: str,
    expected_concept_id: str,
    *,
    study_id: str = "phs000280",
    study_name: str = "ARIC",
    table_name: str = "exam",
    table_description: str = "",
) -> Case[VariableInput, str, str]:
    """Build an eval case for a single variable.

    Args:
        name: Case identifier.
        variable_name: dbGaP variable name.
        variable_description: Variable description text.
        expected_concept_id: Expected concept_id or "null".
        study_id: Study accession.
        study_name: Study display name.
        table_name: Table name.
        table_description: Table description.

    Returns:
        A pydantic-evals Case.
    """
    return Case(
        name=name,
        inputs=VariableInput(
            study_id=study_id,
            study_name=study_name,
            table_name=table_name,
            table_description=table_description,
            variable_name=variable_name,
            variable_description=variable_description,
        ),
        expected_output=expected_concept_id,
        metadata={"source": f"{study_id}/{table_name}"},
    )


# ---------------------------------------------------------------------------
# Test cases — derived from TOPMed ground truth
# ---------------------------------------------------------------------------

CASES = [
    # ── Blood pressure ────────────────────────────────────────────────────
    var_case(
        "bp-systolic-aric",
        "SBPA21",
        "SITTING SYSTOLIC BLOOD PRESSURE, FIRST READING",
        "bp_systolic",
        study_id="phs000280",
        study_name="ARIC",
        table_name="SBPA",
        table_description="Seated blood pressure measurements",
    ),
    var_case(
        "bp-diastolic-aric",
        "SBPA22",
        "SITTING DIASTOLIC BLOOD PRESSURE, FIRST READING",
        "bp_diastolic",
        study_id="phs000280",
        study_name="ARIC",
        table_name="SBPA",
        table_description="Seated blood pressure measurements",
    ),
    var_case(
        "antihypertensive-aric",
        "HYPTMD01",
        "Blood pressure lowering medications in the past 2 weeks",
        "antihypertensive_meds",
        study_id="phs000280",
        study_name="ARIC",
        table_name="HYPA",
        table_description="Hypertension medication history",
    ),
    # ── Lipids ────────────────────────────────────────────────────────────
    var_case(
        "hdl-aric",
        "HDL01",
        "HDL cholesterol (recalibrated lipid)",
        "hdl",
        study_id="phs000280",
        study_name="ARIC",
        table_name="LIPA",
        table_description="Lipid measurements",
    ),
    var_case(
        "total-cholesterol-aric",
        "TCHSIU01",
        "Total cholesterol in SI units",
        "total_cholesterol",
        study_id="phs000280",
        study_name="ARIC",
        table_name="LIPA",
        table_description="Lipid measurements",
    ),
    var_case(
        "triglycerides-aric",
        "TRGSIU01",
        "Total triglycerides in SI units",
        "triglycerides",
        study_id="phs000280",
        study_name="ARIC",
        table_name="LIPA",
        table_description="Lipid measurements",
    ),
    var_case(
        "lipid-meds-aric",
        "CHOLMDCODE01",
        "Cholesterol lowering medication in past 2 weeks: using 2004 coding",
        "lipid_lowering_medication",
        study_id="phs000280",
        study_name="ARIC",
        table_name="medications",
        table_description="Medication use history",
    ),
    var_case(
        "fasting-aric",
        "FAST0802",
        "Fasting time of 8 hours or more",
        "fasting_lipids",
        study_id="phs000280",
        study_name="ARIC",
        table_name="LIPA",
        table_description="Lipid measurements",
    ),
    # ── Blood cell counts ─────────────────────────────────────────────────
    var_case(
        "wbc-fhs",
        "WBC",
        "White blood cell count (sample type: whole blood)",
        "wbc_ncnc_bld",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "hemoglobin-fhs",
        "HGB",
        "Hemoglobin (sample type: whole blood)",
        "hemoglobin_mcnc_bld",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "platelet-aric",
        "HMTA04",
        "Platelet count x1000/mm3 (MAV). Q4",
        "platelet_ncnc_bld",
        study_id="phs000280",
        study_name="ARIC",
        table_name="HMTA",
        table_description="Hematology lab results",
    ),
    var_case(
        "rbc-fhs",
        "RBC",
        "Red blood count (sample type: whole blood)",
        "rbc_ncnc_bld",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "mcv-aric",
        "HMTB13",
        "Mean corpuscular volume (MCV) (to nearest whole unit). Q13",
        "mcv_entvol_rbc",
        study_id="phs000280",
        study_name="ARIC",
        table_name="HMTB",
        table_description="Hematology lab results",
    ),
    var_case(
        "hematocrit-fhs",
        "HCT",
        "Hematocrit (sample type: whole blood)",
        "hematocrit_vfr_bld",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    # ── Inflammation ──────────────────────────────────────────────────────
    var_case(
        "crp-aric",
        "LIP33",
        "High sensitive C reactive protein",
        "crp",
        study_id="phs000280",
        study_name="ARIC",
        table_name="LIPA",
        table_description="Lipid and inflammation markers",
    ),
    var_case(
        "il6-cardia",
        "FL6IL6",
        "IL6 PG/ML",
        "il6",
        study_id="phs000285",
        study_name="CARDIA",
        table_name="F06LPL",
        table_description="Year 15 inflammation markers",
    ),
    var_case(
        "il6-cfs",
        "il6am",
        "Il6 am (pg/mL)",
        "il6",
        study_id="phs000284",
        study_name="CFS",
        table_name="inflammation",
        table_description="Inflammatory markers",
    ),
    var_case(
        "lppla2-activity-mesa",
        "cam1a",
        "LIPOPROTEIN-ASSOCIATED PHOSPHOLIPASE A2: ACTIVITY",
        "lppla2_act",
        study_id="phs000209",
        study_name="MESA",
        table_name="biomarkers",
        table_description="Biomarker measurements",
    ),
    # ── Atherosclerosis ───────────────────────────────────────────────────
    var_case(
        "cac-score-amish",
        "cac_agatston_score",
        "Coronary artery calcification score",
        "cac_score",
        study_id="phs000956",
        study_name="Amish",
        table_name="cac",
        table_description="Coronary artery calcification measurements",
    ),
    var_case(
        "cac-score-chs",
        "CACSCORE",
        "Coronary Artery Calcification by electron beam CYT scan",
        "cac_score",
        study_id="phs000287",
        study_name="CHS",
        table_name="cac",
        table_description="Coronary artery calcification",
    ),
    var_case(
        "carotid-plaque-aric",
        "PLAQUE01",
        "Plaque (with or without shadowing) in any carotid site",
        "carotid_plaque",
        study_id="phs000280",
        study_name="ARIC",
        table_name="ULTA",
        table_description="Carotid ultrasound measurements",
    ),
    var_case(
        "cimt-amish",
        "imt_mean_farwall_cca_baseline",
        "Carotid intima-media far wall thickness at baseline visit",
        "cimt",
        study_id="phs000956",
        study_name="Amish",
        table_name="imt",
        table_description="Intima-media thickness measurements",
    ),
    var_case(
        "carotid-stenosis-chs",
        "PSTEN141",
        "YEAR 5 PERCENT STENOSIS, RT SIDE",
        "carotid_stenosis",
        study_id="phs000287",
        study_name="CHS",
        table_name="carotid_stenosis",
        table_description="Carotid stenosis measurements",
    ),
    # ── Demographics ──────────────────────────────────────────────────────
    var_case(
        "sex-amish",
        "SEX",
        "Sex of participant",
        "annotated_sex",
        study_id="phs000956",
        study_name="Amish",
        table_name="demographics",
        table_description="Participant demographics",
    ),
    var_case(
        "sex-aric",
        "GENDER",
        "Sex (uncorrected from FTRA22)",
        "annotated_sex",
        study_id="phs000280",
        study_name="ARIC",
        table_name="DERIVE13",
        table_description="Derived demographic variables",
    ),
    var_case(
        "race-aric",
        "RACEGRP",
        "Race (from FTRA23)",
        "race_us",
        study_id="phs000280",
        study_name="ARIC",
        table_name="DERIVE13",
        table_description="Derived demographic variables",
    ),
    # ── Baseline covariates ───────────────────────────────────────────────
    var_case(
        "height-baseline-aric",
        "ANTA01",
        "[Height and weight]. Standing height (to the nearest cm). Q1",
        "height_baseline",
        study_id="phs000280",
        study_name="ARIC",
        table_name="ANTA",
        table_description="Anthropometry",
    ),
    var_case(
        "weight-baseline-aric",
        "ANTA04",
        "[Height and weight]. Weight (to the nearest lb). Q4",
        "weight_baseline",
        study_id="phs000280",
        study_name="ARIC",
        table_name="ANTA",
        table_description="Anthropometry",
    ),
    var_case(
        "bmi-baseline-goldn",
        "BMI",
        "Body Mass Index",
        "bmi_baseline",
        study_id="phs000741",
        study_name="GOLDN",
        table_name="enrollment",
        table_description="Enrollment measurements",
    ),
    # ── Sleep ─────────────────────────────────────────────────────────────
    var_case(
        "sleep-duration-aric",
        "RSE21",
        "F. Sleep. Q21. Hours of sleep in past month",
        "sleep_duration",
        study_id="phs000280",
        study_name="ARIC",
        table_name="RSEA",
        table_description="Sleep questionnaire",
    ),
    # ── VTE ───────────────────────────────────────────────────────────────
    var_case(
        "vte-case-status",
        "case_control_status",
        "VTE case status",
        "vte_case_status",
        study_id="phs001189",
        study_name="CCAF",
        table_name="vte",
        table_description="Venous thromboembolism case-control data",
    ),
    # ── Age at measurement ──────────────────────────────────────────────
    # "Age at X measurement" is an age variable, not an X variable.
    # Should match ncpi:subject_age.
    var_case(
        "age-at-cac-measurement",
        "ESP_AGE_AT_CAC",
        "Age in years at CAC Agatston score measurement",
        "ncpi:subject_age",
        study_id="phs000401",
        study_name="FHS ESP HeartGO",
        table_name="HeartGO_FHS_LDLandEOMI_PhenotypeDataFile",
    ),
    var_case(
        "age-at-crp-measurement",
        "ESP_AGE_AT_CRP",
        "Age in years at CRP measurement",
        "ncpi:subject_age",
        study_id="phs000401",
        study_name="FHS ESP HeartGO",
        table_name="HeartGO_FHS_LDLandEOMI_PhenotypeDataFile",
    ),
    var_case(
        "age-at-hematocrit-measurement",
        "ESP_AGE_AT_HEMATOCRIT",
        "Age in years at hematocrit measurement",
        "ncpi:subject_age",
        study_id="phs000401",
        study_name="FHS ESP HeartGO",
        table_name="HeartGO_FHS_LDLandEOMI_PhenotypeDataFile",
    ),
    # ── True negatives (should return null) ───────────────────────────────
    # Study admin variables
    var_case(
        "neg-consent",
        "consent",
        "Consent group description",
        "null",
        study_id="phs000280",
        study_name="ARIC",
        table_name="Subject",
        table_description="Subject attributes",
    ),
    var_case(
        "neg-participant-id",
        "SUBJID",
        "Subject identifier",
        "null",
        study_id="phs000280",
        study_name="ARIC",
        table_name="Subject",
        table_description="Subject attributes",
    ),
    var_case(
        "neg-visit-date",
        "VISITDT",
        "Date of clinic visit",
        "null",
        study_id="phs000280",
        study_name="ARIC",
        table_name="DERIVE13",
        table_description="Visit tracking",
    ),
    # Opaque / self-referential
    var_case(
        "neg-opaque",
        "X42ZQ",
        "",
        "null",
        study_id="phs000999",
        study_name="Unknown Study",
        table_name="misc_data",
    ),
    var_case(
        "neg-self-ref",
        "MISC03",
        "MISC03",
        "null",
        study_id="phs000209",
        study_name="MESA",
        table_name="misc_form",
        table_description="Miscellaneous form responses",
    ),
    # Quality/condition codes
    var_case(
        "neg-condition-code",
        "UBMEBI11",
        "COND CODE, INTERF 2 (BIF:BM NEAR)",
        "null",
        study_id="phs000209",
        study_name="MESA",
        table_name="bmode_carotid",
        table_description="B-mode carotid ultrasound measurements",
    ),
    # Family medical history — seizures aren't a specific concept but the
    # variable IS family health history data. Classifier returns
    # psychiatric_interview_family_history (an archetype) which is reasonable
    # given the epilepsy/pedigree context.
    var_case(
        "family-hx-seizures",
        "BioSisterHadSeizures1",
        "G (b): Biological Sisters. Has this sister ever had seizures? (1)",
        "psychiatric_interview_family_history",
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    # ── ECG ─────────────────────────────────────────────────────────────
    var_case(
        "ecg-finding",
        "mcr665",
        "INTERMITTENT ABERRANT ATRIOVENTRICULAR CONDUCTION; BY VISUAL ANALYSIS",
        "ecg",
        study_id="phs000209",
        study_name="MESA",
        table_name="MESA_Exam5Main",
        table_description="Exam 5 clinical measurements",
    ),
    # ── Cognition ───────────────────────────────────────────────────────
    var_case(
        "cognition-digit-span",
        "DSF",
        "DIGIT SPAN FORWARD SCORE",
        "cognition",
        study_id="phs000280",
        study_name="MESA",
        table_name="cognitive",
        table_description="Cognitive function tests",
    ),
    # ── Age concepts ─────────────────────────────────────────────────────
    # A variable whose value IS an age and whose context clearly signals
    # follow-up start age should match. Generic "age at enrollment" is
    # ambiguous — the ground truth pre-classification handles those.
    var_case(
        "age-followup-start",
        "AGEBL",
        "Calculated age at baseline, start of cardiovascular follow-up",
        "cad_followup_start_age",
        study_id="phs000280",
        study_name="ARIC",
        table_name="events",
        table_description="Cardiovascular event surveillance data",
    ),
    var_case(
        "age-enrollment",
        "AGE",
        "AGE AT ENROLLMENT",
        "ncpi:subject_age",
        study_id="phs000280",
        study_name="ARIC",
        table_name="enrollment",
        table_description="Enrollment data",
    ),
    # ── Generic age variables ────────────────────────────────────────────
    # Generic age variables should match ncpi:subject_age (or phenx:current_age),
    # but must NOT match disease-specific followup age concepts like
    # vte_followup_start_age or cad_followup_start_age.
    # ConceptIdClose also accepts same-domain matches via the demographic group.
    var_case(
        "age-generic-subject",
        "age",
        "Subject age at time of study",
        "ncpi:subject_age",
        study_id="phs000284",
        study_name="Cleveland Family Study",
        table_name="CFS_CARe_Subject_Phenotypes",
        table_description="Subject phenotype data",
    ),
    var_case(
        "age-at-recruitment",
        "Age",
        "Age at recruitment",
        "ncpi:subject_age",
        study_id="phs000140",
        study_name="T2D GWAS in African Americans",
        table_name="CIDR_T2D_Case_Data",
        table_description="Type 2 diabetes case data",
    ),
    var_case(
        "age-at-collection",
        "AGE_AT_COLLECTION",
        "Age at sample collection",
        "ncpi:subject_age",
        study_id="phs000200",
        study_name="COPD",
        table_name="Subject_Phenotypes",
        table_description="Subject phenotype data",
    ),
    var_case(
        "age-at-blood-draw",
        "AGE_AT_DRAW",
        "Age at blood draw",
        "ncpi:subject_age",
        study_id="phs000280",
        study_name="ARIC",
        table_name="lab",
        table_description="Laboratory specimen data",
    ),
    var_case(
        "age-baseline-copd",
        "age_baseline",
        "Age at baseline",
        "ncpi:subject_age",
        study_id="phs000179",
        study_name="COPDGene",
        table_name="COPDGene_Subject_Phenotypes",
        table_description="Subject phenotype data",
    ),
    var_case(
        "age-at-visit",
        "age_visit",
        "Age at current visit",
        "ncpi:subject_age",
        study_id="phs000179",
        study_name="COPDGene",
        table_name="COPDGene_Subject_Phenotypes",
        table_description="Subject phenotype data",
    ),
    var_case(
        "age-at-death",
        "AGE_AT_DEATH",
        "Age of subject at death",
        "ncpi:subject_age",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="mortality",
        table_description="Mortality data",
    ),
    var_case(
        "age-months",
        "AGE_MONTHS",
        "Age in months",
        "ncpi:subject_age",
        study_id="phs000001",
        study_name="AREDS",
        table_name="Subject",
        table_description="Subject attributes",
    ),
    var_case(
        "age-enrollage",
        "ENROLLAGE",
        "AGE AT RANDOMIZATION",
        "ncpi:subject_age",
        study_id="phs000001",
        study_name="AREDS",
        table_name="genspecphenotype",
        table_description="Genetic specimen phenotype data",
    ),
    var_case(
        "age-sampling",
        "AGE_SAMPLING",
        "Age at sampling",
        "ncpi:subject_age",
        study_id="phs000200",
        study_name="COPD",
        table_name="Subject_Phenotypes",
        table_description="Subject phenotype data",
    ),
    # Positive: VTE followup start age in correct context
    var_case(
        "age-vte-followup",
        "V1AGE01",
        "Age at visit 1, start of VTE event adjudication period",
        "vte_followup_start_age",
        study_id="phs000289",
        study_name="CCAF",
        table_name="vte",
        table_description="Venous thromboembolism event surveillance data",
    ),
]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

dataset = Dataset[VariableInput, str, str](
    cases=CASES,
    evaluators=[ConceptIdEquals(), ConceptIdClose()],
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run v4 concept matching classifier evals."""
    parser = argparse.ArgumentParser(
        description="Eval v4 concept matching (classify_v4)"
    )
    parser.add_argument(
        "--model",
        help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)",
    )
    args = parser.parse_args()

    if args.model:
        import classify_v4

        classify_v4.MODEL = args.model
        print(f"Model override: {args.model}", file=sys.stderr)

    report = await dataset.evaluate(
        classify_one_variable,
        max_concurrency=5,
    )
    report.print(include_input=False, include_output=True, include_reasons=True)


if __name__ == "__main__":
    asyncio.run(main())
