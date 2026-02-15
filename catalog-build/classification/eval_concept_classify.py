"""Evals for variable-level concept classification.

Each eval case is a single variable sent individually to the LLM.
This isolates the prompt's ability to assign the right concept without
context effects from neighboring variables.

Usage:
    python eval_concept_classify.py                # Run evals against live LLM
    python eval_concept_classify.py --model anthropic:claude-sonnet-4-5-20250929

Requires:
    pip install pydantic-evals
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, EvaluationReason

from llm_concept_classify import classify_batch, get_agent
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
# Task function: classifies one variable via classify_batch
# ---------------------------------------------------------------------------


async def classify_one_variable(inputs: VariableInput) -> str:
    """Classify a single variable and return its concept string."""
    table = ParsedTable(
        study_id=inputs.study_id,
        dataset_id="eval",
        table_name=inputs.table_name,
        study_name=inputs.study_name,
        description=inputs.table_description,
        variables=[{"name": inputs.variable_name, "description": inputs.variable_description}],
        variable_count=1,
        file_path="eval",
    )
    concepts, _, _ = await classify_batch(
        inputs.study_id,
        inputs.study_name,
        table,
        table.variables,
    )
    if concepts:
        return concepts[0].concept
    return ""


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


@dataclass
class ConceptEquals(Evaluator[VariableInput, str, str]):
    """Check if the returned concept matches the expected concept exactly."""

    def evaluate(self, ctx: EvaluatorContext[VariableInput, str, str]) -> EvaluationReason:
        if ctx.output == ctx.expected_output:
            return EvaluationReason(value=True, reason=ctx.output)
        return EvaluationReason(
            value=False,
            reason=f"expected {ctx.expected_output!r}, got {ctx.output!r}",
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

# Source: phs000001 (AREDS) enrollment_randomization table
# Smoking variables — currently all lumped as "Smoking Status"
# These have meaningfully different semantics and should get distinct concepts.

CASES = [
    # -- Smoking (from phs000001/enrollment_randomization) --
    # SNOMED CT preferred terms verified via Snowstorm API
    var_case(
        "smoking-ever",
        "SMOKEDYN",
        "EVER SMOKED CIGARETTES FOR 6 MONTHS OR MORE (ALL PARTICIPANTS)",
        "History of Smoking",  # SNOMED 10998291000119107
    ),
    var_case(
        "smoking-current",
        "SMKCURR",
        "CURRENTLY SMOKE (ALL PARTICIPANTS)",
        "Current Smoker",  # SNOMED 77176002 (Smoker, PT: Current smoker)
    ),
    var_case(
        "smoking-onset-age",
        "SMKAGEST",
        "AGE STARTED SMOKING (ALL PARTICIPANTS)",
        "Age at Smoking Onset",  # No SNOMED concept — research-only term
    ),
    var_case(
        "smoking-quit-age",
        "SMKAGEQT",
        "AGE QUIT SMOKING (ALL PARTICIPANTS)",
        "Age at Smoking Cessation",  # SNOMED 1221000175102
    ),
    var_case(
        "smoking-cigarettes-per-day",
        "SMKNOCIG",
        "HOW MANY CIGARETTES A DAY SMOKE (ALL PARTICIPANTS)",
        "Cigarette Consumption",  # SNOMED 230056004
    ),
    var_case(
        "smoking-packs-per-day",
        "SMKPACKS",
        "AVERAGE PACKS PER DAY SMOKED (ALL PARTICIPANTS)",
        "Cigarette Consumption",  # SNOMED 230056004
    ),
    # -- Blood pressure (from phs000001/enrollment_randomization) --
    # SNOMED CT preferred terms verified via Snowstorm API
    var_case(
        "bp-diastolic-1",
        "SITDIAS1",
        "SITTING DIASTOLIC BLOOD PRESSURE AT BASELINE (ALL PARTICIPANTS)",
        "Diastolic Blood Pressure",  # SNOMED 271650006
    ),
    var_case(
        "bp-diastolic-2",
        "SITDIAS2",
        "SITTING DIASTOLIC BLOOD PRESSURE (2ND READING) AT BASELINE (ALL PARTICIPANTS)",
        "Diastolic Blood Pressure",  # SNOMED 271650006
    ),
    var_case(
        "bp-systolic-1",
        "SITSYST1",
        "SITTING SYSTOLIC BLOOD PRESSURE AT BASELINE (ALL PARTICIPANTS)",
        "Systolic Blood Pressure",  # SNOMED 271649006
    ),
    var_case(
        "bp-systolic-2",
        "SITSYST2",
        "SITTING SYSTOLIC BLOOD PRESSURE (2ND READING) AT BASELINE (ALL PARTICIPANTS)",
        "Systolic Blood Pressure",  # SNOMED 271649006
    ),
    var_case(
        "bp-hypertension-history",
        "BPHIGHYN",
        "HISTORY OF HIGH BLOOD PRESSURE (ALL PARTICIPANTS)",
        "History of Hypertension",  # SNOMED 161501007
    ),
    var_case(
        "bp-medication",
        "BPMEDNOW",
        "CURRENTLY TAKING MEDICATION FOR HIGH BLOOD PRESSURE (ALL PARTICIPANTS)",
        "Antihypertensive Therapy",  # SNOMED 182823005
    ),
]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

dataset = Dataset[VariableInput, str, str](
    cases=CASES,
    evaluators=[ConceptEquals()],
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run concept classification evals."""
    parser = argparse.ArgumentParser(description="Eval concept classification")
    parser.add_argument(
        "--model",
        help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)",
    )
    args = parser.parse_args()

    if args.model:
        import llm_concept_classify

        llm_concept_classify.MODEL = args.model
        print(f"Model override: {args.model}", file=sys.stderr)

    report = await dataset.evaluate(classify_one_variable)
    report.print(include_input=True, include_output=True)


if __name__ == "__main__":
    asyncio.run(main())
