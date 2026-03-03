"""Summarize classification results across all completed studies.

Reads output/llm-concepts-v4/*.json and prints:
  - Per-concept match counts grouped by NCPI category (via ISA hierarchy)
  - Match rate and source breakdown (ground_truth vs llm)
  - Coverage by NCPI category
  - Optionally: per-concept variable samples with --examples

Usage:
    python summarize_v3.py              # concept summary
    python summarize_v3.py --examples   # show example variables per concept
    python summarize_v3.py --nulls      # show unmatched variable samples
    python summarize_v3.py --by-study   # show per-study match rates
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts-v4"
ISA_PATH = SCRIPT_DIR / "output" / "concept-isa.json"
NCPI_PATH = SCRIPT_DIR / "output" / "ncpi-categories.json"
VOCAB_PATH = SCRIPT_DIR / "output" / "concept-vocabulary.json"
PHENX_VOCAB_PATH = SCRIPT_DIR / "output" / "phenx-concept-vocabulary.json"


def load_isa_ancestors():
    """Load ISA and build concept -> NCPI category mapping.

    Returns:
        Tuple of (concept_to_ncpi_category, children_of).
    """
    if not ISA_PATH.exists():
        return {}, {}

    with open(ISA_PATH) as f:
        isa = json.load(f)

    # Build parent lookup
    parent_of = {}
    children_of = defaultdict(list)
    for rel in isa:
        parent_of[rel["child"]] = rel["parent"]
        children_of[rel["parent"]].append(rel["child"])

    # Walk up to find NCPI category for each concept
    ncpi_ids = set()
    if NCPI_PATH.exists():
        with open(NCPI_PATH) as f:
            ncpi_ids = {c["concept_id"] for c in json.load(f)}

    concept_to_category = {}
    for rel in isa:
        concept = rel["child"]
        current = concept
        visited = set()
        while current and current not in ncpi_ids and current not in visited:
            visited.add(current)
            current = parent_of.get(current)
        if current and current in ncpi_ids:
            concept_to_category[concept] = current

    # NCPI categories map to themselves
    for nid in ncpi_ids:
        concept_to_category[nid] = nid

    return concept_to_category, children_of


def load_concept_names():
    """Load display names for all concepts across vocabularies.

    Maps both namespaced and bare IDs so lookups work regardless of format.

    Returns:
        Dict mapping concept_id to display name.
    """
    names = {}

    if VOCAB_PATH.exists():
        with open(VOCAB_PATH) as f:
            for entry in json.load(f):
                cid = entry["concept_id"]
                names[cid] = entry["name"]
                # Also store without namespace prefix for bare-ID lookups
                if ":" in cid:
                    names[cid.split(":", 1)[1]] = entry["name"]

    if PHENX_VOCAB_PATH.exists():
        with open(PHENX_VOCAB_PATH) as f:
            for entry in json.load(f):
                cid = entry["concept_id"]
                names[cid] = entry["name"]
                if ":" in cid:
                    names[cid.split(":", 1)[1]] = entry["name"]

    if NCPI_PATH.exists():
        with open(NCPI_PATH) as f:
            for entry in json.load(f):
                names[entry["concept_id"]] = entry["name"]

    return names


def main():
    """Summarize classification output."""
    parser = argparse.ArgumentParser(description="Summarize classification results")
    parser.add_argument(
        "--examples", action="store_true",
        help="Show example variables for each concept",
    )
    parser.add_argument(
        "--nulls", action="store_true",
        help="Show sample unmatched variables",
    )
    parser.add_argument(
        "--concept", help="Filter to a specific concept_id",
    )
    parser.add_argument(
        "--by-study", action="store_true",
        help="Show per-study match rates",
    )
    args = parser.parse_args()

    files = sorted(OUTPUT_DIR.glob("*.json"))
    if not files:
        print(f"No output files in {OUTPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    concept_to_category, children_of = load_isa_ancestors()
    concept_names = load_concept_names()

    # Collect stats
    concept_vars = defaultdict(list)  # concept_id -> [(study, table, name, desc, conf, src)]
    study_stats = {}  # study_id -> {total, matched}
    total_vars = 0
    total_matched = 0
    total_gt = 0
    total_llm = 0
    studies_done = 0

    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        studies_done += 1
        study_total = 0
        study_matched = 0

        for table in data.get("tables", []):
            for v in table.get("variables", []):
                total_vars += 1
                study_total += 1
                cid = v.get("concept_id")
                src = v.get("source", "llm")
                if cid is not None:
                    total_matched += 1
                    study_matched += 1
                    if src == "ground_truth":
                        total_gt += 1
                    else:
                        total_llm += 1
                    concept_vars[cid].append((
                        data["studyId"],
                        table["tableName"],
                        v["name"],
                        v.get("description", "")[:60],
                        v.get("confidence", ""),
                        src,
                    ))
                else:
                    concept_vars["_null"].append((
                        data["studyId"],
                        table["tableName"],
                        v["name"],
                        v.get("description", "")[:60],
                        v.get("confidence", ""),
                        src,
                    ))

        study_stats[data["studyId"]] = {
            "total": study_total,
            "matched": study_matched,
            "name": data.get("studyName", data["studyId"]),
        }

    # Print summary
    print(f"Studies: {studies_done}")
    print(f"Variables: {total_vars:,}")
    if total_vars:
        print(f"Matched: {total_matched:,} ({total_matched/total_vars*100:.1f}%)")
    else:
        print("Matched: 0")
    print(f"  ground_truth: {total_gt:,}")
    print(f"  llm: {total_llm:,}")
    print(f"Unmatched: {total_vars - total_matched:,}")
    active_concepts = {k for k in concept_vars if k != "_null"}
    print(f"Concepts matched: {len(active_concepts)}")
    print()

    # Filter to specific concept if requested
    if args.concept:
        cid = args.concept
        entries = concept_vars.get(cid, [])
        name = concept_names.get(cid, cid)
        cat = concept_to_category.get(cid, "?")
        print(f"--- {cid} ({name}) [{cat}]: {len(entries)} matches ---")
        for study, table, name, desc, conf, src in entries:
            print(f"  {study}/{table}: {name} — {desc} [{conf}, {src}]")
        return

    # Per-study stats
    if args.by_study:
        print(f"{'study_id':<16} {'name':<40} {'total':>7} {'matched':>7} {'rate':>6}")
        print("-" * 80)
        sorted_studies = sorted(
            study_stats.items(),
            key=lambda x: x[1]["matched"],
            reverse=True,
        )
        for sid, stats in sorted_studies[:50]:
            rate = stats["matched"] / stats["total"] * 100 if stats["total"] else 0
            name = stats["name"][:38]
            print(f"  {sid:<14} {name:<40} {stats['total']:>7,} {stats['matched']:>7,} {rate:>5.1f}%")
        if len(sorted_studies) > 50:
            print(f"  ... +{len(sorted_studies)-50} more studies")
        return

    # Group concepts by NCPI category
    category_concepts = defaultdict(list)  # ncpi_id -> [(concept_id, count)]
    uncategorized = []

    for cid in sorted(active_concepts):
        count = len(concept_vars[cid])
        cat = concept_to_category.get(cid)
        if cat:
            category_concepts[cat].append((cid, count))
        else:
            uncategorized.append((cid, count))

    # Load NCPI categories for ordering
    ncpi_order = []
    if NCPI_PATH.exists():
        with open(NCPI_PATH) as f:
            ncpi_order = [c["concept_id"] for c in json.load(f)]

    # Print by category
    header = f"{'concept_id':<40} {'count':>6}  {'high':>4} {'med':>4} {'low':>4}  {'gt':>4} {'llm':>4}"
    divider = "-" * 85

    for cat_id in ncpi_order:
        concepts_in_cat = category_concepts.get(cat_id, [])
        if not concepts_in_cat:
            continue

        cat_name = concept_names.get(cat_id, cat_id)
        cat_total = sum(c for _, c in concepts_in_cat)
        cat_studies = len({e[0] for cid, _ in concepts_in_cat for e in concept_vars[cid]})
        print(f"## {cat_name} ({cat_id})  — {cat_total:,} vars, {cat_studies} studies")
        print(header)
        print(divider)

        for cid, n in sorted(concepts_in_cat, key=lambda x: x[1], reverse=True):
            entries = concept_vars[cid]
            high = sum(1 for e in entries if e[4] == "high")
            med = sum(1 for e in entries if e[4] == "medium")
            low = sum(1 for e in entries if e[4] == "low")
            gt = sum(1 for e in entries if e[5] == "ground_truth")
            llm = sum(1 for e in entries if e[5] == "llm")
            name = concept_names.get(cid, "")
            label = f"{cid}" if not name else f"{cid} ({name})"
            print(f"  {label:<38} {n:>6}  {high:>4} {med:>4} {low:>4}  {gt:>4} {llm:>4}")

            if args.examples:
                seen_studies = set()
                shown = 0
                for study, table, name, desc, conf, src in entries:
                    if shown >= 5:
                        break
                    if study not in seen_studies:
                        seen_studies.add(study)
                        print(f"    {study}/{table}: {name} — {desc} [{conf}]")
                        shown += 1
                print()

        print()

    # Uncategorized concepts
    if uncategorized:
        unc_total = sum(c for _, c in uncategorized)
        print(f"## Uncategorized — {unc_total:,} vars")
        print(header)
        print(divider)
        for cid, n in sorted(uncategorized, key=lambda x: x[1], reverse=True):
            entries = concept_vars[cid]
            high = sum(1 for e in entries if e[4] == "high")
            med = sum(1 for e in entries if e[4] == "medium")
            low = sum(1 for e in entries if e[4] == "low")
            gt = sum(1 for e in entries if e[5] == "ground_truth")
            llm = sum(1 for e in entries if e[5] == "llm")
            print(f"  {cid:<38} {n:>6}  {high:>4} {med:>4} {low:>4}  {gt:>4} {llm:>4}")
        print()

    # Category coverage summary
    print("## Category Coverage")
    print(f"{'category':<35} {'concepts':>8} {'vars':>8} {'studies':>8}")
    print("-" * 65)
    for cat_id in ncpi_order:
        concepts_in_cat = category_concepts.get(cat_id, [])
        cat_name = concept_names.get(cat_id, cat_id)
        cat_total = sum(c for _, c in concepts_in_cat)
        cat_studies = len({e[0] for cid, _ in concepts_in_cat for e in concept_vars[cid]}) if concepts_in_cat else 0
        marker = "" if concepts_in_cat else " (empty)"
        print(
            f"  {cat_name:<33} {len(concepts_in_cat):>8} "
            f"{cat_total:>8,} {cat_studies:>8}{marker}"
        )
    print()

    # Null samples
    if args.nulls:
        nulls = concept_vars.get("_null", [])
        print(f"\n--- Unmatched samples ({len(nulls):,} total, showing 20) ---")
        import random
        samples = random.sample(nulls, min(20, len(nulls)))
        for study, table, name, desc, conf, src in samples:
            print(f"  {study}/{table}: {name} — {desc}")


if __name__ == "__main__":
    main()
