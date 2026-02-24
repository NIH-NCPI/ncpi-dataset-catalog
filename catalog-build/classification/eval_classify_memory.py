"""Evals for classify_with_memory.py (v2 variable-level concept classification).

Each eval case sends a single variable to the LLM with an empty concept bank.
This tests the prompt's ability to assign the right concept in isolation —
no bank influence, no neighboring variable effects.

Usage:
    python eval_classify_memory.py                # Run evals against live LLM
    python eval_classify_memory.py --model anthropic:claude-sonnet-4-5-20250929

Requires:
    pip install pydantic-evals
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic import BaseModel

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, EvaluationReason

from classify_with_memory import (
    ConceptBank,
    _build_bank_lookup,
    classify_batch,
    make_agent,
)
from models import ParsedTable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = __import__("pathlib").Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")


# ---------------------------------------------------------------------------
# Eval input/output models
# ---------------------------------------------------------------------------


class VariableInput(BaseModel):
    """A single variable with its table context."""

    study_id: str
    study_name: str
    table_name: str
    table_description: str
    variable_name: str
    variable_description: str


# ---------------------------------------------------------------------------
# Task function: classifies one variable via v2 pipeline (empty bank)
# ---------------------------------------------------------------------------


async def classify_one_variable(inputs: VariableInput) -> str:
    """Classify a single variable and return its concept string."""
    bank = ConceptBank()
    agent = make_agent(bank, 1000)
    bank_lookup = _build_bank_lookup(bank)

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
    result, _, _ = await classify_batch(
        agent,
        bank_lookup,
        inputs.study_id,
        inputs.study_name,
        table,
        table.variables,
    )
    if result.variables:
        return result.variables[0].concept
    return ""


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy comparison."""
    import re

    return " ".join(re.sub(r"[^a-z0-9\s]", " ", s.lower()).split())


@dataclass
class ConceptEquals(Evaluator[VariableInput, str, str]):
    """Check if the returned concept matches the expected concept exactly."""

    def evaluate(
        self, ctx: EvaluatorContext[VariableInput, str, str]
    ) -> EvaluationReason:
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


_SYNONYM_PAIRS = [
    ("disease", "disorder"),
    ("condition", "disorder"),
    ("consumption", "per day"),
    ("history", "status"),
    ("illness", "medical history"),
    ("illness", "medical encounter"),
    ("acute illness", "medical history"),
    ("acute illness", "medical encounter"),
    ("acute illness", "acute disease"),
    ("cigarette smoking history", "smoking history"),
    ("cigarette packs per day", "cigarette consumption"),
    ("initiation", "onset"),
    ("cessation age", "age at smoking cessation"),
    ("smoking cessation age", "age at smoking cessation"),
    ("packs per day smoked", "smoking packs per day"),
    ("packs per day smoked", "packs per day"),
    ("packs per day smoked", "cigarettes per day"),
    ("packs per day", "cigarettes per day"),
]


@dataclass
class ConceptClose(Evaluator[VariableInput, str, str]):
    """Check if the concept is close enough (normalized, substring, or synonym)."""

    def evaluate(
        self, ctx: EvaluatorContext[VariableInput, str, str]
    ) -> EvaluationReason:
        norm_out = _normalize(ctx.output)
        norm_exp = _normalize(ctx.expected_output)
        # Exact normalized match
        if norm_out == norm_exp:
            return EvaluationReason(
                value=True,
                reason=f"close: {ctx.output!r} ~ {ctx.expected_output!r}",
            )
        # Substring match (either direction)
        if norm_exp in norm_out or norm_out in norm_exp:
            return EvaluationReason(
                value=True,
                reason=f"close (substring): {ctx.output!r} ~ {ctx.expected_output!r}",
            )
        # Known synonym pairs
        for a, b in _SYNONYM_PAIRS:
            swapped_out = norm_out.replace(a, b)
            swapped_exp = norm_exp.replace(a, b)
            if swapped_out == norm_exp or norm_out == swapped_exp:
                return EvaluationReason(
                    value=True,
                    reason=f"close (synonym): {ctx.output!r} ~ {ctx.expected_output!r}",
                )
        return EvaluationReason(
            value=False,
            reason=f"not close: {ctx.output!r} vs {ctx.expected_output!r}",
        )


# ---------------------------------------------------------------------------
# Helper to build cases
# ---------------------------------------------------------------------------


def var_case(
    name: str,
    variable_name: str,
    variable_description: str,
    expected_concept: str,
    *,
    study_id: str = "phs000001",
    study_name: str = "Age-Related Eye Disease Study (AREDS)",
    table_name: str = "enrollment_randomization",
    table_description: str = "",
) -> Case[VariableInput, str, str]:
    """Build an eval case for a single variable."""
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
        expected_output=expected_concept,
        metadata={"source": f"{study_id}/{table_name}"},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Source studies: phs000001 (AREDS), phs000007 (FHS), phs000286 (JHS)
# SNOMED CT / UMLS preferred terms verified where noted.

CASES = [
    # ── Smoking granularity (phs000001) ──────────────────────────────────
    # Distinct aspects of smoking should NOT all be "Smoking Status"
    var_case(
        "smoking-ever",
        "SMOKEDYN",
        "EVER SMOKED CIGARETTES FOR 6 MONTHS OR MORE (ALL PARTICIPANTS)",
        "Smoking History",  # "Cigarette" is implied; LLM generalizes correctly
    ),
    var_case(
        "smoking-current",
        "SMKCURR",
        "CURRENTLY SMOKE (ALL PARTICIPANTS)",
        "Current Smoking Status",
    ),
    var_case(
        "smoking-onset-age",
        "SMKAGEST",
        "AGE STARTED SMOKING (ALL PARTICIPANTS)",
        "Smoking Initiation Age",  # Semantically equivalent to "Age at Starting Smoking"
    ),
    var_case(
        "smoking-quit-age",
        "SMKAGEQT",
        "AGE QUIT SMOKING (ALL PARTICIPANTS)",
        "Smoking Cessation Age",  # Semantically equivalent to "Age at Stopping Smoking"
    ),
    var_case(
        "smoking-cigs-per-day",
        "SMKNOCIG",
        "HOW MANY CIGARETTES A DAY SMOKE (ALL PARTICIPANTS)",
        "Cigarettes Per Day",
    ),
    var_case(
        "smoking-packs-per-day",
        "SMKPACKS",
        "AVERAGE PACKS PER DAY SMOKED (ALL PARTICIPANTS)",
        "Packs Per Day Smoked",  # Keeps unit and action from description
    ),
    # ── Blood pressure (phs000001) ───────────────────────────────────────
    var_case(
        "bp-diastolic",
        "SITDIAS1",
        "SITTING DIASTOLIC BLOOD PRESSURE AT BASELINE (ALL PARTICIPANTS)",
        "Sitting Diastolic Blood Pressure",  # Body position is clinically meaningful; hierarchy groups under Diastolic BP
    ),
    var_case(
        "bp-systolic",
        "SITSYST1",
        "SITTING SYSTOLIC BLOOD PRESSURE AT BASELINE (ALL PARTICIPANTS)",
        "Sitting Systolic Blood Pressure",  # Body position is clinically meaningful; hierarchy groups under Systolic BP
    ),
    var_case(
        "bp-hypertension-hx",
        "BPHIGHYN",
        "HISTORY OF HIGH BLOOD PRESSURE (ALL PARTICIPANTS)",
        "Hypertension History",
    ),
    var_case(
        "bp-medication",
        "BPMEDNOW",
        "CURRENTLY TAKING MEDICATION FOR HIGH BLOOD PRESSURE (ALL PARTICIPANTS)",
        "Antihypertensive Medication Use",
    ),
    # ── Medical history granularity (phs000007 FHS) ──────────────────────
    # Specific conditions should NOT be lumped as "Medical History"
    var_case(
        "hx-hysterectomy",
        "FP120",
        "HYSTERECTOMY IN INTERIM",
        "Hysterectomy History",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
    ),
    var_case(
        "hx-thyroid",
        "FP102",
        "DIAGNOSED WITH THYROID CONDITION IN INTERIM",
        "Thyroid Disorder History",  # SNOMED CT prefers "disorder" over "disease"
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
    ),
    var_case(
        "hx-hospitalization",
        "FP037",
        "HOSPITALIZATION IN INTERIM",
        "Hospitalization History",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
    ),
    var_case(
        "hx-illness-generic",
        "FP039",
        "ILLNESS WITH VISIT TO DOCTOR",
        "Acute Disease",  # SNOMED CT 2704003; generic illness, not a specific condition
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
    ),
    # ── Study administration (phs000001) ─────────────────────────────────
    # Should NOT all be lumped as "Study Administration"
    var_case(
        "admin-subject-id",
        "ID2",
        "DUMMY ID NUMBER",
        "Participant Identifier",
    ),
    var_case(
        "admin-consent",
        "consent",
        "Consent group description",
        "Informed Consent",
        table_name="AREDS_Subject",
        table_description="Subject attributes",
    ),
    var_case(
        "admin-treatment",
        "TRTCAT",
        "AREDS TREATMENT ASSIGNMENT (ALL PARTICIPANTS)",
        "Treatment Assignment",
    ),
    var_case(
        "admin-followup-time",
        "FOLTIME",
        "YEARS FROM RANDOMIZATION TO DATE OF FOLLOW-UP INTERVIEW (ALL PARTICIPANTS)",
        "Follow-Up Duration",
        table_name="followup",
    ),
    # ── ECG granularity (phs000286 JHS) ──────────────────────────────────
    # Individual ECG measurements should get SPECIFIC concepts,
    # NOT the generic "Electrocardiography" umbrella.
    var_case(
        "ecg-qrs-duration",
        "QRSDUR",
        "QRS Duration (ms)",
        "QRS Duration",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    var_case(
        "ecg-qt-interval",
        "QTINT",
        "QT Interval (ms)",
        "QT Interval",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    var_case(
        "ecg-pr-interval",
        "PRINT",
        "PR Interval (ms)",
        "PR Interval",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    var_case(
        "ecg-heart-rate",
        "VENRATE",
        "Ventricular Heart Rate (bpm)",
        "Ventricular Heart Rate",  # Description says "Ventricular Heart Rate" — clinically specific
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    var_case(
        "ecg-qrs-axis",
        "QRSAXIS",
        "QRS Axis (degrees)",
        "QRS Axis",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    var_case(
        "ecg-cornell-voltage",
        "CORNV",
        "Cornell Voltage (RaVL + SV3, mV)",
        "Cornell Voltage",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    # ── Body measurements ────────────────────────────────────────────────
    var_case(
        "bmi",
        "BMI",
        "Body mass index (kg/m^2)",
        "Body Mass Index",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="anthro",
        table_description="Anthropometric measurements",
    ),
    var_case(
        "waist-circumference",
        "WAIST",
        "Waist circumference (cm)",
        "Waist Circumference",
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="anthro",
        table_description="Anthropometric measurements",
    ),
    # ── Demographics ─────────────────────────────────────────────────────
    var_case(
        "demo-age",
        "AGE",
        "AGE AT ENROLLMENT (ALL PARTICIPANTS)",
        "Age at Enrollment",  # "at Enrollment" is meaningful context, not a visit qualifier
    ),
    var_case(
        "demo-sex",
        "SEX",
        "GENDER (ALL PARTICIPANTS)",
        "Sex",
    ),
    var_case(
        "demo-race",
        "RACE",
        "RACE (ALL PARTICIPANTS)",
        "Race",
    ),
    var_case(
        "demo-ethnicity",
        "ETHNIC",
        "ARE YOU HISPANIC OR LATINO (ALL PARTICIPANTS)",
        "Hispanic or Latino Ethnicity",  # "or" is lowercase in proper title case
    ),
    var_case(
        "demo-race-not-combined",
        "RACEGRP",
        "SELF-REPORTED RACE/ETHNICITY",
        "Race",  # Even combined vars should classify to the dominant construct
        study_id="phs000280",
        study_name="MESA",
        table_name="demographics",
        table_description="Participant demographics",
    ),
    # ── CBC analytes (should NOT lump under "Complete Blood Count") ────
    var_case(
        "cbc-wbc",
        "WBC",
        "WHITE BLOOD CELL COUNT (THOUSAND/UL)",
        "White Blood Cell Count",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "cbc-hemoglobin",
        "HGB",
        "HEMOGLOBIN (G/DL)",
        "Hemoglobin",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "cbc-platelet",
        "PLT",
        "PLATELET COUNT (THOUSAND/UL)",
        "Platelet Count",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    var_case(
        "cbc-mcv",
        "MCV",
        "MEAN CORPUSCULAR VOLUME (FL)",
        "Mean Corpuscular Volume",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
        table_description="Exam 23 lab results",
    ),
    # ── Urinalysis analytes (should NOT lump under "Urinalysis") ─────
    var_case(
        "urine-albumin",
        "UMALB",
        "URINE ALBUMIN (MG/L)",
        "Urine Albumin",
        study_id="phs000280",
        study_name="MESA",
        table_name="lab_results",
        table_description="Laboratory results",
    ),
    var_case(
        "urine-creatinine",
        "UMCREAT",
        "URINE CREATININE (MG/DL)",
        "Urine Creatinine",
        study_id="phs000280",
        study_name="MESA",
        table_name="lab_results",
        table_description="Laboratory results",
    ),
    # ── Cognition tests (should NOT lump under "Cognition Assessment") ─
    var_case(
        "cognition-dsf",
        "DSF",
        "DIGIT SPAN FORWARD SCORE",
        "Digit Span Forward",  # Forward and Backward are distinct tests
        study_id="phs000280",
        study_name="MESA",
        table_name="cognitive",
        table_description="Cognitive function tests",
    ),
    var_case(
        "cognition-trails-b",
        "TRLB",
        "TRAIL MAKING TEST PART B TIME (SECONDS)",
        "Trail Making Test Part B Time",  # "Time" is the specific measurement from this test
        study_id="phs000280",
        study_name="MESA",
        table_name="cognitive",
        table_description="Cognitive function tests",
    ),
    # ── Echocardiography (should NOT lump under "Echocardiography") ──
    var_case(
        "echo-lvef",
        "LVEF",
        "LEFT VENTRICULAR EJECTION FRACTION (%)",
        "Left Ventricular Ejection Fraction",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="echo",
        table_description="Echocardiography measurements",
    ),
    # ── Family history (phs000576) ─────────────────────────────────────
    # Questions about a RELATIVE's condition should be "Family History of X",
    # NOT the participant-level concept.
    var_case(
        "famhx-sister-seizures",
        "BioSisterHadSeizures1",
        "G (b): Biological Sisters . Has this sister ever had seizures? (1)",
        "Family History of Seizure Disorder",
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    var_case(
        "famhx-aunt-seizures",
        "AuntSeizures1",
        "H (a): Mother's Biological Sisters (Maternal Aunts). Has the aunt ever had seizures. (1)",
        "Family History of Seizure Disorder",
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    var_case(
        "famhx-mother-diabetes",
        "MOMDIAB",
        "WAS YOUR MOTHER EVER TOLD SHE HAD DIABETES",
        "Family History of Diabetes",
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_23s",
    ),
    # ── Family member demographics (phs000576) ────────────────────────
    # Questions about a relative's age/vital status should NOT use
    # participant-level concepts like "Vital Status" or "Age".
    var_case(
        "famhx-mother-alive",
        "BirthMotherAlive",
        "A: Biological Mother. Is the birth mother alive?",
        "Maternal Vital Status",
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    var_case(
        "famhx-mother-birthyr",
        "BirthMotherBirthYr",
        "A: Biological Mother. What is the mothers approximate year of birth or age? yyyy",
        "Maternal Birth Year",
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    var_case(
        "famhx-father-alive",
        "BirthFatherAlive",
        "B: Biological Father. Is the birth father alive?",
        "Paternal Vital Status",  # "Paternal" is the standard clinical term for father
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    # ── Opaque / unclassifiable ──────────────────────────────────────────
    # Truly opaque variables should get "Needs Review" instead of a guess
    var_case(
        "opaque-no-description",
        "X42ZQ",
        "",
        "Needs Review",
        study_id="phs000999",
        study_name="Unknown Study",
        table_name="misc_data",
    ),
    var_case(
        "opaque-misleading-abbrev",
        "UBMEAI29",
        "COND CODE, INTERF 4 (LT COM CAR:OPT ANG)",
        "Needs Review",  # COT Q2: quality/process metadata, not a clinical concept
        study_id="phs000209",
        study_name="Multi-Ethnic Study of Atherosclerosis (MESA)",
        table_name="bmode_carotid",
        table_description="B-mode carotid ultrasound measurements",
    ),
    var_case(
        "opaque-misc-self-ref",
        "MISC03",
        "MISC03",
        "Needs Review",
        study_id="phs000209",
        study_name="Multi-Ethnic Study of Atherosclerosis (MESA)",
        table_name="misc_form",
        table_description="Miscellaneous form responses",
    ),
    # ── COT Q1: Subject (participant vs relative) ──────────────────────
    # Relative's demographic attribute MUST NOT get participant-level concept
    var_case(
        "cot-relative-sister-age",
        "BioSisterAgeBirthYr1",
        "G (b): Biological Sisters. Approximate age or year of birth (1)",
        "Sister Birth Year",  # Description explicitly says "Sisters", not generic "Sibling"
        study_id="phs000576",
        study_name="Epilepsy Phenome/Genome Project (EPGP)",
        table_name="pedigree",
        table_description="Family pedigree data",
    ),
    # ── COT Q2: Content type (quality metadata vs clinical) ───────────
    # Condition codes / interference flags are NOT clinical measurements
    var_case(
        "cot-quality-cond-code",
        "UBMEBI11",
        "COND CODE, INTERF 2 (BIF:BM NEAR)",
        "Needs Review",
        study_id="phs000209",
        study_name="Multi-Ethnic Study of Atherosclerosis (MESA)",
        table_name="bmode_carotid",
        table_description="B-mode carotid ultrasound measurements",
    ),
    # ── COT Q4: Specificity (instrument vs measurement) ──────────────
    # Should NOT get "Electrocardiography" umbrella
    var_case(
        "cot-ecg-not-umbrella",
        "mcr665",
        "INTERMITTENT ABERRANT ATRIOVENTRICULAR CONDUCTION; BY VISUAL ANALYSIS",
        "Intermittent Aberrant Atrioventricular Conduction",  # Keep "Intermittent" — it's a distinct finding
        study_id="phs000209",
        study_name="Multi-Ethnic Study of Atherosclerosis (MESA)",
        table_name="MESA_Exam5Main",
        table_description="Exam 5 clinical measurements",
    ),
    # ── Pregnancy context (phs000314 GAIT/Clubfoot) ──────────────────
    # "during pregnancy" is clinically meaningful, not a qualifier to strip
    var_case(
        "pregnancy-smoking",
        "Smk",
        "Smoking during pregnancy",
        "Smoking During Pregnancy",  # Pregnancy context is the key qualifier; "Maternal" is optional
        study_id="phs000314",
        study_name="Genetic Associations in Idiopathic Talipes Equinovarus (GAIT)",
        table_name="CIDR_Clubfoot_Subject_Phenotypes",
    ),
    var_case(
        "pregnancy-diabetes",
        "Diab",
        "Diabetes during pregnancy",
        "Gestational Diabetes",
        study_id="phs000314",
        study_name="Genetic Associations in Idiopathic Talipes Equinovarus (GAIT)",
        table_name="CIDR_Clubfoot_Subject_Phenotypes",
    ),
    var_case(
        "pregnancy-trimester",
        "SmkTri",
        "Trimester when smoking occurred",
        "Smoking Exposure Trimester",  # Specific: which trimester the smoking exposure happened
        study_id="phs000314",
        study_name="Genetic Associations in Idiopathic Talipes Equinovarus (GAIT)",
        table_name="CIDR_Clubfoot_Subject_Phenotypes",
    ),
    # ── Twin zygosity (phs000314 GAIT/Clubfoot) ───────────────────
    var_case(
        "twin-zygosity",
        "TWINTYPE",
        "Twin zygosity",
        "Twin Zygosity",
        study_id="phs000314",
        study_name="Genetic Associations in Idiopathic Talipes Equinovarus (GAIT)",
        table_name="CIDR_Clubfoot_Pedigree",
        table_description="Family pedigree data",
    ),
    # ── ECG lead-specific (phs000286 JHS) ─────────────────────────
    var_case(
        "cot-ecg-t-amplitude",
        "ecga241",
        "T_AMPV6 - T- Amplitude in lead V6",
        "T-Wave Amplitude in Lead V6",  # Lead-specific; hierarchy links to parent "T-Wave Amplitude"
        study_id="phs000286",
        study_name="Jackson Heart Study (JHS)",
        table_name="ecg12",
        table_description="12-lead ECG measurements",
    ),
    # ── Rule 5: Strip study logistics ────────────────────────────
    # Visit numbers, exam cycles, "in interim" should be stripped
    var_case(
        "strip-visit-number",
        "SBPA21",
        "SITTING SYSTOLIC BLOOD PRESSURE, VISIT 3",
        "Sitting Systolic Blood Pressure",  # "Visit 3" stripped
        study_id="phs000280",
        study_name="MESA",
        table_name="exam3",
        table_description="Exam 3 clinical measurements",
    ),
    var_case(
        "strip-exam-cycle",
        "TCHOL",
        "TOTAL CHOLESTEROL (MG/DL) AT EXAM 7",
        "Total Cholesterol",  # "at Exam 7" stripped
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="ex0_7s",
        table_description="Exam 7 lab results",
    ),
    # ── Rule 5: Keep laterality ──────────────────────────────────
    var_case(
        "keep-laterality",
        "LOSFEMBN",
        "LEFT FEMORAL NECK BONE MINERAL DENSITY (G/CM2)",
        "Left Femoral Neck Bone Mineral Density",  # "Left" is clinical context, keep it
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="dxa",
        table_description="DXA bone density measurements",
    ),
    # ── Rule 7: Condition vs Treatment ───────────────────────────
    # Distinct concepts even when from the same domain
    var_case(
        "condition-diabetes",
        "DIAB",
        "HISTORY OF DIABETES MELLITUS",
        "Diabetes Mellitus History",
        study_id="phs000280",
        study_name="MESA",
        table_name="medical_history",
        table_description="Medical history questionnaire",
    ),
    var_case(
        "treatment-diabetes",
        "DIABRX",
        "CURRENTLY TAKING DIABETES MEDICATION",
        "Diabetes Medication Use",  # Treatment, not condition
        study_id="phs000280",
        study_name="MESA",
        table_name="medications",
        table_description="Current medication use",
    ),
    var_case(
        "treatment-statin",
        "STATIN",
        "CURRENTLY TAKING STATIN MEDICATION FOR CHOLESTEROL",
        "Statin Medication Use",  # Treatment, not the lipid measurement
        study_id="phs000280",
        study_name="MESA",
        table_name="medications",
        table_description="Current medication use",
    ),
    # ── Rule 8: Composite variables ──────────────────────────────
    # Variable from a composite section — classify the specific variable, not the section
    var_case(
        "composite-height-from-hw",
        "ANTA01",
        "[Height and weight]. Standing height (to the nearest cm). Q1",
        "Standing Height",  # "Standing" preserves measurement context from description
        study_id="phs000280",
        study_name="ARIC",
        table_name="ANTA",
        table_description="Anthropometry",
    ),
    var_case(
        "composite-weight-from-hw",
        "ANTA04",
        "[Height and weight]. Weight (to the nearest lb). Q4",
        "Body Weight",  # "Body" is standard clinical prefix; more specific than bare "Weight"
        study_id="phs000280",
        study_name="ARIC",
        table_name="ANTA",
        table_description="Anthropometry",
    ),
    var_case(
        "composite-race-ethnicity",
        "RACE_CODE",
        "RACE and ETHNICITY - Summary code string from combining responses given over exams",
        "Race",  # LLM classifies to the dominant construct even from combined fields
        study_id="phs000007",
        study_name="Framingham Heart Study",
        table_name="vr_raceall_2011_a_1257s",
    ),
]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

dataset = Dataset[VariableInput, str, str](
    cases=CASES,
    evaluators=[ConceptEquals(), ConceptClose()],
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run v2 concept classification evals."""
    parser = argparse.ArgumentParser(
        description="Eval v2 concept classification (classify_with_memory)"
    )
    parser.add_argument(
        "--model",
        help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)",
    )
    args = parser.parse_args()

    if args.model:
        import classify_with_memory

        classify_with_memory.MODEL = args.model
        print(f"Model override: {args.model}", file=sys.stderr)

    report = await dataset.evaluate(classify_one_variable)
    report.print(include_input=False, include_output=True, include_reasons=True)


if __name__ == "__main__":
    asyncio.run(main())
