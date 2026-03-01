"""Evals for build_archetypes.py — LLM rejection of misclassified variables.

Each eval case sends a small set of variables (some belonging to the parent
concept, some not) to the archetype LLM and checks whether misclassified
variables land in `_rejected`.

Usage:
    python eval_archetypes.py                # Run evals
    python eval_archetypes.py --model anthropic:claude-sonnet-4-5-20250929

Requires:
    pip install pydantic-evals
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluationReason, EvaluatorContext

from build_archetypes import (
    Archetype,
    ArchetypeTree,
    _call_assign_variables,
    _call_define_archetypes,
)

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")


# ---------------------------------------------------------------------------
# Eval input/output models
# ---------------------------------------------------------------------------


class DefineInput(BaseModel):
    """Input for archetype definition eval."""

    parent_concept: str
    variables: list[dict]


class DefineExpectation(BaseModel):
    """Expected output for archetype definition eval."""

    should_reject: list[str]
    should_keep: list[str]


class AssignInput(BaseModel):
    """Input for archetype assignment eval."""

    parent_concept: str
    archetypes: list[dict]
    variables: list[dict]


class AssignExpectation(BaseModel):
    """Expected output for archetype assignment eval."""

    should_reject: list[str]
    should_keep: list[str]


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------


async def run_define(inputs: DefineInput) -> ArchetypeTree:
    """Call archetype definition LLM."""
    return await _call_define_archetypes(inputs.parent_concept, inputs.variables)


async def run_assign(inputs: AssignInput) -> dict[str, str]:
    """Call archetype assignment LLM."""
    archetypes = [Archetype(**a) for a in inputs.archetypes]
    return await _call_assign_variables(
        inputs.parent_concept, archetypes, inputs.variables
    )


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


@dataclass
class DefineRejectsCorrectly(Evaluator[DefineInput, ArchetypeTree, DefineExpectation]):
    """Check that expected variables are rejected and kept correctly."""

    def evaluate(
        self, ctx: EvaluatorContext[DefineInput, ArchetypeTree, DefineExpectation]
    ) -> EvaluationReason:
        """Evaluate rejection accuracy.

        Args:
            ctx: Evaluation context.

        Returns:
            Pass/fail with reason.
        """
        tree = ctx.output
        exp = ctx.expected_output

        # Collect rejected and kept variable names
        rejected_names: set[str] = set()
        kept_names: set[str] = set()
        for cat in tree.categories:
            if cat.concept_id == "_rejected":
                rejected_names.update(v.lower() for v in cat.variables)
            else:
                kept_names.update(v.lower() for v in cat.variables)

        # Check should_reject vars are in _rejected
        missed_rejects = []
        for vname in exp.should_reject:
            if vname.lower() not in rejected_names:
                missed_rejects.append(vname)

        # Check should_keep vars are NOT in _rejected
        wrongly_rejected = []
        for vname in exp.should_keep:
            if vname.lower() in rejected_names:
                wrongly_rejected.append(vname)

        issues = []
        if missed_rejects:
            issues.append(f"should reject but didn't: {missed_rejects}")
        if wrongly_rejected:
            issues.append(f"wrongly rejected: {wrongly_rejected}")

        if not issues:
            return EvaluationReason(
                value=True,
                reason=f"correctly rejected {len(exp.should_reject)}, "
                       f"kept {len(exp.should_keep)}",
            )
        return EvaluationReason(value=False, reason="; ".join(issues))


@dataclass
class AssignRejectsCorrectly(Evaluator[AssignInput, dict, AssignExpectation]):
    """Check that assignment-mode rejects misclassified variables."""

    def evaluate(
        self, ctx: EvaluatorContext[AssignInput, dict, AssignExpectation]
    ) -> EvaluationReason:
        """Evaluate rejection accuracy in assignment mode.

        Args:
            ctx: Evaluation context.

        Returns:
            Pass/fail with reason.
        """
        assignments = ctx.output
        exp = ctx.expected_output

        rejected = {k.lower() for k, v in assignments.items() if v == "_rejected"}
        kept = {k.lower() for k, v in assignments.items() if v != "_rejected"}

        missed_rejects = [v for v in exp.should_reject if v.lower() not in rejected]
        wrongly_rejected = [v for v in exp.should_keep if v.lower() in rejected]

        issues = []
        if missed_rejects:
            issues.append(f"should reject but didn't: {missed_rejects}")
        if wrongly_rejected:
            issues.append(f"wrongly rejected: {wrongly_rejected}")

        if not issues:
            return EvaluationReason(
                value=True,
                reason=f"correctly rejected {len(exp.should_reject)}, "
                       f"kept {len(exp.should_keep)}",
            )
        return EvaluationReason(value=False, reason="; ".join(issues))


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Variables that clearly don't belong under VTE followup start age
VTE_REJECTED_VARS = [
    {"name": "AGE", "description": "Subject age at enrollment"},
    {"name": "age_visit", "description": "Age at study visit"},
    {"name": "AGE_AT_DEATH", "description": "Age of subject at death"},
    {"name": "ENROLLAGE", "description": "Age at enrollment"},
    {"name": "AgeatTestingYears", "description": "Age at testing in years"},
    {"name": "gestational_age", "description": "Gestational age in weeks"},
    {"name": "NEC_Dx_DOL", "description": "Day of life at NEC diagnosis"},
    {"name": "DSTRAGED", "description": "Age at start of diarrheal episode"},
]

# Variables that DO belong under VTE followup start age
VTE_KEPT_VARS = [
    {"name": "AbovekneeDeepVeinThrombosis_age", "description": "Age at above-knee DVT"},
    {"name": "PulmEmbolusWithDpVnThrom_Age", "description": "Age at PE with DVT"},
    {"name": "age_clot", "description": "Age at blood clot event"},
    {"name": "VascularAccessThrombosis_Age", "description": "Age at vascular access thrombosis"},
]

# Variables that clearly don't belong under ECG
ECG_REJECTED_VARS = [
    {"name": "BMI", "description": "Body mass index"},
    {"name": "WEIGHT_KG", "description": "Body weight in kilograms"},
    {"name": "SMOKING_STATUS", "description": "Current smoking status"},
]

# Variables that DO belong under ECG
ECG_KEPT_VARS = [
    {"name": "AFIB", "description": "Atrial fibrillation detected on ECG"},
    {"name": "QT_INT", "description": "QT interval in milliseconds"},
    {"name": "PR_INT", "description": "PR interval in milliseconds"},
    {"name": "QRS_DUR", "description": "QRS duration in milliseconds"},
    {"name": "HRTRATE", "description": "Heart rate from ECG tracing"},
]

# Variables that don't belong under CAD followup start age
CAD_REJECTED_VARS = [
    {"name": "age_at_visit", "description": "Age at study visit"},
    {"name": "enrollment_age", "description": "Age at study enrollment"},
    {"name": "maternal_age", "description": "Maternal age at delivery"},
    {"name": "AGE_SAMPLING", "description": "Age at sample collection"},
]

# Variables that DO belong under CAD followup start age
CAD_KEPT_VARS = [
    {"name": "AGEBL", "description": "Calculated age at baseline, start of cardiovascular follow-up"},
    {"name": "cad_followup_start_age", "description": "Age at start of CAD event surveillance"},
]

DEFINE_CASES = [
    Case(
        name="vte-rejects-generic-age",
        inputs=DefineInput(
            parent_concept="vte_followup_start_age",
            variables=VTE_REJECTED_VARS + VTE_KEPT_VARS,
        ),
        expected_output=DefineExpectation(
            should_reject=[v["name"] for v in VTE_REJECTED_VARS],
            should_keep=[v["name"] for v in VTE_KEPT_VARS],
        ),
        metadata={"concept": "vte_followup_start_age"},
    ),
    Case(
        name="ecg-rejects-non-ecg",
        inputs=DefineInput(
            parent_concept="topmed:ecg",
            variables=ECG_REJECTED_VARS + ECG_KEPT_VARS,
        ),
        expected_output=DefineExpectation(
            should_reject=[v["name"] for v in ECG_REJECTED_VARS],
            should_keep=[v["name"] for v in ECG_KEPT_VARS],
        ),
        metadata={"concept": "topmed:ecg"},
    ),
    Case(
        name="cad-rejects-generic-age",
        inputs=DefineInput(
            parent_concept="cad_followup_start_age",
            variables=CAD_REJECTED_VARS + CAD_KEPT_VARS,
        ),
        expected_output=DefineExpectation(
            should_reject=[v["name"] for v in CAD_REJECTED_VARS],
            should_keep=[v["name"] for v in CAD_KEPT_VARS],
        ),
        metadata={"concept": "cad_followup_start_age"},
    ),
]

# Assignment eval: archetypes already defined, check rejection in batch assign
ASSIGN_CASES = [
    Case(
        name="assign-vte-rejects-generic",
        inputs=AssignInput(
            parent_concept="vte_followup_start_age",
            archetypes=[
                {
                    "concept_id": "thrombosis_event_age",
                    "name": "Thrombosis Event Age",
                    "description": "Age at DVT, PE, or other thrombotic event",
                    "variables": [],
                },
                {
                    "concept_id": "vascular_access_thrombosis",
                    "name": "Vascular Access Thrombosis Age",
                    "description": "Age at vascular access related thrombosis",
                    "variables": [],
                },
            ],
            variables=[
                {"name": "age_clot", "description": "Age at blood clot event"},
                {"name": "AGE", "description": "Subject age at enrollment"},
                {"name": "ENROLLAGE", "description": "Age at study enrollment"},
                {"name": "PulmEmbolusWithDpVnThrom_Age", "description": "Age at PE with DVT"},
            ],
        ),
        expected_output=AssignExpectation(
            should_reject=["AGE", "ENROLLAGE"],
            should_keep=["age_clot", "PulmEmbolusWithDpVnThrom_Age"],
        ),
        metadata={"concept": "vte_followup_start_age"},
    ),
    Case(
        name="assign-ecg-rejects-bmi",
        inputs=AssignInput(
            parent_concept="topmed:ecg",
            archetypes=[
                {
                    "concept_id": "atrial_fibrillation",
                    "name": "ECG Atrial Fibrillation",
                    "description": "Atrial fibrillation detection on ECG",
                    "variables": [],
                },
                {
                    "concept_id": "qt_interval",
                    "name": "QT Interval",
                    "description": "QT interval measurement from ECG",
                    "variables": [],
                },
            ],
            variables=[
                {"name": "AFIB", "description": "Atrial fibrillation detected"},
                {"name": "BMI", "description": "Body mass index"},
                {"name": "QT_MS", "description": "QT interval in milliseconds"},
                {"name": "WEIGHT", "description": "Body weight in kg"},
            ],
        ),
        expected_output=AssignExpectation(
            should_reject=["BMI", "WEIGHT"],
            should_keep=["AFIB", "QT_MS"],
        ),
        metadata={"concept": "topmed:ecg"},
    ),
]


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


def build_define_dataset() -> Dataset[DefineInput, ArchetypeTree, DefineExpectation]:
    """Build the archetype definition eval dataset."""
    return Dataset(
        cases=DEFINE_CASES,
        evaluators=[DefineRejectsCorrectly()],
    )


def build_assign_dataset() -> Dataset[AssignInput, dict, AssignExpectation]:
    """Build the archetype assignment eval dataset."""
    return Dataset(
        cases=ASSIGN_CASES,
        evaluators=[AssignRejectsCorrectly()],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> None:
    """Run archetype rejection evals.

    Args:
        args: Parsed command-line arguments.
    """
    if args.model:
        import build_archetypes
        build_archetypes.MODEL = args.model
        print(f"Model override: {args.model}", file=sys.stderr)

    print("=" * 60)
    print("Archetype Definition — Rejection Evals")
    print("=" * 60)
    define_ds = build_define_dataset()
    define_report = await define_ds.evaluate(run_define)
    define_report.print()

    print()
    print("=" * 60)
    print("Archetype Assignment — Rejection Evals")
    print("=" * 60)
    assign_ds = build_assign_dataset()
    assign_report = await assign_ds.evaluate(run_assign)
    assign_report.print()

    # Summary
    total = len(DEFINE_CASES) + len(ASSIGN_CASES)
    print(f"\nTotal eval cases: {total}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Run archetype rejection evals"
    )
    parser.add_argument(
        "--model", help="Override model (e.g. anthropic:claude-sonnet-4-5-20250929)"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
