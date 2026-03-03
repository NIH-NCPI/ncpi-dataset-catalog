#!/usr/bin/env python3
"""Re-classify variables rejected by the archetype builder.

Reads reclassify-studies.txt (written by build_archetypes.py), finds
variables with concept_id=null in those study output files, sends them
through the classifier, and patches results back in place.

Usage:
    python reclassify_rejected.py              # Process all affected studies
    python reclassify_rejected.py --dry-run    # Show stats without calling LLM

Requires reclassify-studies.txt from a prior `make archetypes` run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Clear sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from classify_v4 import (
    PHENX_VOCAB_PATH,
    VOCAB_PATH,
    BatchItem,
    _namespace_concept_id,
    classify_batch,
    load_vocabulary,
    make_agent,
    pack_batches,
)
from models import ParsedTable

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

OUTPUT = SCRIPT_DIR / "output"
LLM_DIR = OUTPUT / "llm-concepts-v4"
RECLASSIFY_PATH = OUTPUT / "archetypes" / "reclassify-studies.txt"

DEFAULT_CONCURRENCY = 10


def _load_reject_sources() -> set[str]:
    """Identify concepts that produced rejected variables.

    Reads archetype cache files for _rejected categories and returns
    the parent concept_ids. These are excluded from the reclassify
    vocabulary to prevent re-misclassification.

    Returns:
        Set of concept_ids that had rejected variables.
    """
    sources: set[str] = set()
    cache_dir = OUTPUT / "archetypes"
    if not cache_dir.exists():
        return sources

    import glob
    for cache_path in sorted(cache_dir.glob("*.json")):
        with open(cache_path) as f:
            tree = json.load(f)
        has_rejected = any(
            c["concept_id"] == "_rejected" for c in tree.get("categories", [])
        )
        if not has_rejected:
            continue
        # Derive concept_id from filename
        bare = cache_path.stem  # e.g. "topmed_ecg" or "vte_followup_start_age"
        for prefix in ("topmed_", "phenx_", "ncpi_"):
            if bare.startswith(prefix):
                concept_id = prefix.rstrip("_") + ":" + bare[len(prefix):]
                break
        else:
            concept_id = bare
        sources.add(concept_id)

    return sources


def load_affected_studies() -> list[str]:
    """Read study IDs from reclassify-studies.txt.

    Returns:
        List of study IDs.
    """
    if not RECLASSIFY_PATH.exists():
        print("No reclassify-studies.txt found — run make archetypes first",
              file=sys.stderr)
        sys.exit(1)
    return [
        line.strip() for line in RECLASSIFY_PATH.read_text().splitlines()
        if line.strip()
    ]


def collect_null_variables(study_id: str) -> tuple[dict, list[tuple[str, int, int]]]:
    """Find variables with concept_id=null in a study output file.

    Args:
        study_id: Study accession (e.g. phs000007).

    Returns:
        Tuple of (study_data, null_locations) where null_locations is
        [(table_name, table_idx, var_idx), ...].
    """
    path = LLM_DIR / f"{study_id}.json"
    if not path.exists():
        return {}, []

    with open(path) as f:
        data = json.load(f)

    null_locs: list[tuple[str, int, int]] = []
    for ti, table in enumerate(data.get("tables", [])):
        for vi, var in enumerate(table.get("variables", [])):
            if var.get("concept_id") is None and var.get("source") == "rejected":
                null_locs.append((table.get("tableName", f"table_{ti}"), ti, vi))

    return data, null_locs


async def reclassify_study(
    agent,
    valid_ids: set[str],
    study_id: str,
    semaphore: asyncio.Semaphore,
) -> tuple[int, int]:
    """Re-classify null-concept variables in one study.

    Args:
        agent: The classifier agent.
        valid_ids: Valid concept IDs.
        study_id: Study accession.
        semaphore: Concurrency limiter.

    Returns:
        Tuple of (total_null, newly_matched).
    """
    data, null_locs = collect_null_variables(study_id)
    if not null_locs:
        return 0, 0

    # Group null vars by table
    tables_vars: dict[int, list[tuple[int, dict]]] = {}
    for table_name, ti, vi in null_locs:
        var = data["tables"][ti]["variables"][vi]
        tables_vars.setdefault(ti, []).append((vi, var))

    # Build BatchItems from the null variables
    study_name = data.get("studyName", study_id)
    batch_items: list[BatchItem] = []

    for ti, var_pairs in tables_vars.items():
        table_data = data["tables"][ti]
        # Create a ParsedTable stub
        parsed_table = ParsedTable(
            study_id=study_id,
            dataset_id=table_data.get("datasetId", ""),
            table_name=table_data.get("tableName", f"table_{ti}"),
            study_name=study_name,
            description=table_data.get("description", ""),
            variables=[
                {"name": v["name"], "description": v.get("description", "")}
                for _, v in var_pairs
            ],
            variable_count=len(var_pairs),
            file_path="reclassify",
        )
        # Variables as list of dicts for the batch
        llm_vars = [
            {"name": v["name"], "description": v.get("description", "")}
            for _, v in var_pairs
        ]
        batch_items.append((parsed_table, llm_vars))

    # Pack and classify
    batches = pack_batches(batch_items)
    newly_matched = 0

    for batch in batches:
        async with semaphore:
            result, _, _ = await classify_batch(
                agent, valid_ids, study_id, study_name, batch
            )

        # Patch results back into data
        for table_result in result.tables:
            # Find the matching table index
            ti_match = None
            for ti, table_data in enumerate(data["tables"]):
                if table_data.get("tableName") == table_result.table_name:
                    ti_match = ti
                    break
            if ti_match is None:
                continue

            for mv in table_result.variables:
                # Find the variable in the table and update it
                for vi, var in enumerate(data["tables"][ti_match]["variables"]):
                    if var["name"] == mv.variable_name and var.get("concept_id") is None:
                        var["concept_id"] = _namespace_concept_id(mv.concept_id)
                        var["confidence"] = mv.confidence
                        var["source"] = "reclassify"
                        newly_matched += 1
                        break

    # Write patched file
    path = LLM_DIR / f"{study_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return len(null_locs), newly_matched


async def main_async(args: argparse.Namespace) -> None:
    """Run reclassification pipeline.

    Args:
        args: Parsed command-line arguments.
    """
    study_ids = load_affected_studies()
    print(f"Studies to reclassify: {len(study_ids)}", file=sys.stderr)

    # Scan for null variables
    total_null = 0
    studies_with_nulls: list[str] = []
    for sid in study_ids:
        _, null_locs = collect_null_variables(sid)
        if null_locs:
            total_null += len(null_locs)
            studies_with_nulls.append(sid)

    print(f"Studies with null variables: {len(studies_with_nulls)}", file=sys.stderr)
    print(f"Total null variables to reclassify: {total_null:,}", file=sys.stderr)

    if not studies_with_nulls:
        print("Nothing to reclassify.", file=sys.stderr)
        return

    if args.dry_run:
        print("\n--- Dry run: no LLM calls ---", file=sys.stderr)
        return

    # Load vocab — exclude archetypes (keeps prompt under token limit)
    # and exclude concepts that rejected vars came FROM (prevents re-misclassification).
    reject_sources = _load_reject_sources()
    vocab = [
        v for v in load_vocabulary(VOCAB_PATH, PHENX_VOCAB_PATH)
        if v.get("type") != "archetype" and v["concept_id"] not in reject_sources
    ]
    if reject_sources:
        print(f"Excluding {len(reject_sources)} source concepts: "
              f"{', '.join(sorted(reject_sources))}", file=sys.stderr)
    print(f"Vocabulary: {len(vocab)} concepts", file=sys.stderr)
    valid_ids = {v["concept_id"] for v in vocab}
    agent = make_agent(vocab)
    semaphore = asyncio.Semaphore(args.concurrency)

    start = time.time()
    results = await asyncio.gather(*[
        reclassify_study(agent, valid_ids, sid, semaphore)
        for sid in studies_with_nulls
    ])

    total_null_processed = sum(r[0] for r in results)
    total_matched = sum(r[1] for r in results)
    elapsed = time.time() - start

    print(
        f"\nDone: {len(studies_with_nulls)} studies, "
        f"{total_null_processed:,} null vars, "
        f"{total_matched:,} newly matched "
        f"({total_matched/total_null_processed*100:.1f}%), "
        f"{elapsed:.0f}s",
        file=sys.stderr,
    )


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Re-classify rejected variables"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show stats without calling LLM",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent LLM calls (default: {DEFAULT_CONCURRENCY})",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
