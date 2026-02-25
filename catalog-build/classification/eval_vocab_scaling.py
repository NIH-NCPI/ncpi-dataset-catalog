"""Test classifier accuracy as concept vocabulary scales from 78 to 5000+.

Uses the existing 44 eval cases from eval_v3_topmed.py but inflates the
concept vocabulary with realistic distractors drawn from the v1 concept
summary (high-frequency concept names from actual dbGaP data).

Usage:
    python eval_vocab_scaling.py                    # Run default tiers (78, 500, 1000, ...)
    python eval_vocab_scaling.py --tiers 500 1000   # Run specific tiers
    python eval_vocab_scaling.py --tiers 78         # Baseline only
    python eval_vocab_scaling.py --incremental      # 500, 1000, 1500, ... until failure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from pydantic_evals import Dataset

from classify_v3_topmed import (
    MatchDeps,
    build_system_prompt,
    classify_batch,
    format_vocab_for_prompt,
    load_vocabulary,
    make_agent,
    MODEL,
    VOCAB_PATH,
)
from eval_v3_topmed import CASES, ConceptIdClose, ConceptIdEquals, VariableInput
from models import ParsedTable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

V1_SUMMARY_PATH = SCRIPT_DIR / "output" / "concept-summary.json"

# ---------------------------------------------------------------------------
# Build distractor concepts from v1 output
# ---------------------------------------------------------------------------


def _concept_id_from_name(name: str) -> str:
    """Convert a v1 concept name to a snake_case concept_id.

    Args:
        name: Title Case concept name from v1.

    Returns:
        snake_case identifier.
    """
    # Lowercase, replace non-alphanum with underscore, collapse multiples
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


def load_distractors(
    v1_summary_path: Path,
    real_concept_ids: set[str],
    max_count: int = 500,
) -> list[dict]:
    """Load v1 concepts as distractors, excluding any that overlap with real concepts.

    Args:
        v1_summary_path: Path to v1 concept-summary.json.
        real_concept_ids: Set of concept_ids already in the real vocabulary.
        max_count: Maximum number of distractors to return.

    Returns:
        List of distractor concept dicts in vocabulary format.
    """
    with open(v1_summary_path) as f:
        data = json.load(f)

    # v1 concepts sorted by studyCount (cross-study frequency)
    v1_concepts = sorted(
        data["concepts"].items(),
        key=lambda x: (-x[1]["studyCount"], -x[1]["count"]),
    )

    # Build distractor set — skip concepts whose generated id overlaps real ones,
    # or whose name is too generic (Study Administration, Age, etc.)
    skip_names = {
        "Study Administration", "Age", "Sex", "Race/Ethnicity",
        "Participant Identifier", "Informed Consent", "Sample Identifier",
        "Subject Identifier", "Analyte Type", "Tumor Status",
        "Histological Type", "Needs Review",
    }
    # Also build a set of words from real concept descriptions for fuzzy overlap

    distractors = []
    seen_ids = set(real_concept_ids)
    for name, stats in v1_concepts:
        if name in skip_names:
            continue
        cid = _concept_id_from_name(name)
        if cid in seen_ids:
            continue
        # Skip very short ids that might collide
        if len(cid) < 4:
            continue
        seen_ids.add(cid)
        distractors.append({
            "concept_id": cid,
            "name": name,
            "description": name,  # v1 only has the name, use it as description
            "domain": "distractor",
            "example_variables": [],
        })
        if len(distractors) >= max_count:
            break

    return distractors


def load_distractors_all(
    v1_summary_path: Path,
    real_concept_ids: set[str],
) -> list[dict]:
    """Load ALL v1 concepts as distractors (no cap).

    Args:
        v1_summary_path: Path to v1 concept-summary.json.
        real_concept_ids: Set of concept_ids already in the real vocabulary.

    Returns:
        List of distractor concept dicts.
    """
    return load_distractors(v1_summary_path, real_concept_ids, max_count=999999)


# ---------------------------------------------------------------------------
# Build inflated vocabularies
# ---------------------------------------------------------------------------


def build_vocab_at_size(
    real_vocab: list[dict],
    distractors: list[dict],
    target_size: int,
) -> list[dict] | None:
    """Build a vocabulary at a specific size.

    Args:
        real_vocab: The real 78-concept vocabulary.
        distractors: Pool of distractor concepts.
        target_size: Desired total concept count.

    Returns:
        Vocabulary list, or None if not enough distractors.
    """
    n_real = len({v["concept_id"] for v in real_vocab})
    if target_size <= n_real:
        return list(real_vocab)
    n_needed = target_size - n_real
    if len(distractors) < n_needed:
        return None
    return list(real_vocab) + distractors[:n_needed]


# ---------------------------------------------------------------------------
# Eval runner (adapted from eval_v3_topmed.py)
# ---------------------------------------------------------------------------


async def classify_one_variable_with_vocab(
    inputs: VariableInput,
    vocab: list[dict],
) -> str:
    """Classify a single variable using a specific vocabulary.

    Args:
        inputs: Variable input data.
        vocab: The concept vocabulary to use.

    Returns:
        concept_id or 'null'.
    """
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
    result, _, _ = await classify_batch(
        agent,
        valid_ids,
        inputs.study_id,
        inputs.study_name,
        table,
        table.variables,
    )
    if result.variables:
        cid = result.variables[0].concept_id
        return cid if cid is not None else "null"
    return "null"


async def run_tier(tier_size: int, vocab: list[dict], verbose: bool = True) -> float:
    """Run all eval cases against a specific vocabulary size.

    Args:
        tier_size: Number of concepts in this tier.
        vocab: The concept vocabulary.
        verbose: Print full report.

    Returns:
        Exact-match pass rate (0.0 to 1.0).
    """
    n_concepts = len({v["concept_id"] for v in vocab})
    print(f"\n{'='*70}")
    print(f"TIER: {n_concepts} concepts ({tier_size} requested)")
    print(f"{'='*70}\n")

    # Count prompt tokens roughly
    vocab_text = format_vocab_for_prompt(vocab)
    est_tokens = len(vocab_text) // 4
    print(f"  Vocab prompt size: ~{est_tokens:,} tokens ({len(vocab_text):,} chars)")

    async def _classify(inputs: VariableInput) -> str:
        return await classify_one_variable_with_vocab(inputs, vocab)

    dataset = Dataset[VariableInput, str, str](
        cases=CASES,
        evaluators=[ConceptIdEquals(), ConceptIdClose()],
    )

    report = await dataset.evaluate(_classify)
    if verbose:
        report.print(include_input=False, include_output=True, include_reasons=True)

    # Extract pass rate from report averages
    avgs = report.averages()
    rate = avgs.assertions if avgs and avgs.assertions is not None else 0.0
    print(f"\n  >> Assertion pass rate: {rate*100:.1f}%")
    return rate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run vocabulary scaling evals."""
    parser = argparse.ArgumentParser(
        description="Test classifier accuracy at different vocabulary sizes"
    )
    parser.add_argument(
        "--tiers",
        type=int,
        nargs="+",
        help="Specific tier sizes to test (e.g. --tiers 500 1000 2000)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Start at 500, increment by 500 until accuracy drops below 90%%",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=500,
        help="Step size for --incremental mode (default: 500)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Stop when exact-match rate drops below this (default: 0.90)",
    )
    args = parser.parse_args()

    # Load real vocab
    real_vocab = load_vocabulary(VOCAB_PATH)
    real_ids = {v["concept_id"] for v in real_vocab}
    n_real = len(real_ids)
    print(f"Real vocabulary: {n_real} concepts")

    # Load ALL distractors from v1
    if not V1_SUMMARY_PATH.exists():
        print(f"ERROR: v1 summary not found: {V1_SUMMARY_PATH}", file=sys.stderr)
        sys.exit(1)

    distractors = load_distractors_all(V1_SUMMARY_PATH, real_ids)
    max_possible = n_real + len(distractors)
    print(f"Distractors available: {len(distractors)} (max tier: {max_possible})")

    # Determine which tiers to run
    results: list[tuple[int, float]] = []

    if args.incremental:
        tier_size = args.step
        while tier_size <= max_possible:
            vocab = build_vocab_at_size(real_vocab, distractors, tier_size)
            if vocab is None:
                print(f"\nNot enough distractors for tier {tier_size}, stopping.")
                break
            rate = await run_tier(tier_size, vocab, verbose=False)
            results.append((tier_size, rate))
            if rate < args.threshold:
                print(f"\n  ** Accuracy {rate*100:.1f}% < {args.threshold*100:.0f}% threshold — stopping.")
                break
            tier_size += args.step
    elif args.tiers:
        for tier_size in args.tiers:
            vocab = build_vocab_at_size(real_vocab, distractors, tier_size)
            if vocab is None:
                print(f"\nNot enough distractors for tier {tier_size}, skipping.")
                continue
            rate = await run_tier(tier_size, vocab)
            results.append((tier_size, rate))
    else:
        # Default: baseline + a few tiers
        for tier_size in [n_real, 500, 1000, 2000, 5000]:
            vocab = build_vocab_at_size(real_vocab, distractors, tier_size)
            if vocab is None:
                print(f"\nNot enough distractors for tier {tier_size}, stopping.")
                break
            rate = await run_tier(tier_size, vocab)
            results.append((tier_size, rate))

    # Print summary table
    if results:
        print(f"\n{'='*50}")
        print("SCALING SUMMARY")
        print(f"{'='*50}")
        print(f"{'Concepts':>10}  {'Exact Match':>12}  {'Status'}")
        print(f"{'-'*10}  {'-'*12}  {'-'*10}")
        for size, rate in results:
            status = "PASS" if rate >= args.threshold else "FAIL"
            print(f"{size:>10}  {rate*100:>11.1f}%  {status}")


if __name__ == "__main__":
    asyncio.run(main())
