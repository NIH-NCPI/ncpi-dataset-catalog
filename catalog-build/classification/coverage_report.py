"""Generate coverage statistics for variable classifications.

Usage:
    python coverage_report.py                    # Report for all studies
    python coverage_report.py --study phs000007  # Report for one study
    python coverage_report.py --top 20           # Show top 20 in each ranking
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from models import Classification, CoverageStats, ParsedTable
from parse_var_reports import CACHE_FILE, load_cache

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CLASSIFICATIONS_FILE = OUTPUT_DIR / "classifications.json"
COVERAGE_FILE = OUTPUT_DIR / "coverage-report.json"


def load_classifications(path: Path) -> list[Classification]:
    """Load classifications from JSON.

    Args:
        path: Path to the classifications JSON file.

    Returns:
        List of Classification objects.
    """
    with open(path) as f:
        data = json.load(f)
    return [Classification(**d) for d in data]


def compute_study_coverage(
    tables: list[ParsedTable],
    classifications: list[Classification],
) -> CoverageStats:
    """Compute coverage stats for a single study's tables.

    Args:
        tables: All tables for this study.
        classifications: All classifications for this study.

    Returns:
        CoverageStats for the study.
    """
    study_id = tables[0].study_id
    study_name = tables[0].study_name

    total_tables = len(tables)
    total_vars = sum(t.variable_count for t in tables)

    classified_dataset_ids = {c.dataset_id for c in classifications}
    classified_tables = sum(1 for t in tables if t.dataset_id in classified_dataset_ids)
    classified_vars = sum(c.variable_count for c in classifications)

    concepts: dict[str, int] = defaultdict(int)
    for c in classifications:
        concepts[c.concept] += c.variable_count

    rate = (classified_vars / total_vars * 100) if total_vars > 0 else 0

    return CoverageStats(
        study_id=study_id,
        study_name=study_name,
        total_tables=total_tables,
        classified_tables=classified_tables,
        unclassified_tables=total_tables - classified_tables,
        total_variables=total_vars,
        classified_variables=classified_vars,
        unclassified_variables=total_vars - classified_vars,
        classification_rate=round(rate, 1),
        concepts=dict(sorted(concepts.items(), key=lambda x: -x[1])),
    )


def generate_report(
    tables: list[ParsedTable],
    classifications: list[Classification],
    study_filter: str | None = None,
    top_n: int = 10,
) -> list[CoverageStats]:
    """Generate coverage report for all or one study.

    Args:
        tables: All parsed tables.
        classifications: All classifications.
        study_filter: If set, only report on this study.
        top_n: Number of entries in top-N rankings.

    Returns:
        List of CoverageStats, one per study.
    """
    # Group by study
    tables_by_study: dict[str, list[ParsedTable]] = defaultdict(list)
    for t in tables:
        tables_by_study[t.study_id].append(t)

    class_by_study: dict[str, list[Classification]] = defaultdict(list)
    for c in classifications:
        class_by_study[c.study_id].append(c)

    study_ids = sorted(tables_by_study.keys())
    if study_filter:
        study_ids = [s for s in study_ids if s == study_filter]

    stats_list: list[CoverageStats] = []
    for study_id in study_ids:
        study_tables = tables_by_study[study_id]
        study_class = class_by_study.get(study_id, [])
        stats = compute_study_coverage(study_tables, study_class)
        stats_list.append(stats)

    # Print report
    total_vars = sum(s.total_variables for s in stats_list)
    classified_vars = sum(s.classified_variables for s in stats_list)
    total_tables_count = sum(s.total_tables for s in stats_list)
    classified_tables_count = sum(s.classified_tables for s in stats_list)
    overall_rate = (classified_vars / total_vars * 100) if total_vars > 0 else 0

    print("=" * 80)
    print("VARIABLE CLASSIFICATION COVERAGE REPORT")
    print("=" * 80)
    print(
        f"\nOverall: {classified_vars:,} / {total_vars:,} variables classified"
        f" ({overall_rate:.1f}%)"
    )
    print(
        f"Tables:  {classified_tables_count:,} / {total_tables_count:,} tables classified"
    )
    print(f"Studies: {len(stats_list)}")

    # Top studies by unclassified variables
    by_unclassified = sorted(stats_list, key=lambda s: -s.unclassified_variables)
    print(f"\nTop {top_n} studies by UNCLASSIFIED variables:")
    print(f"  {'Study':<14s} {'Name':<40s} {'Unclassified':>12s} {'Total':>10s}")
    print(f"  {'-'*14} {'-'*40} {'-'*12} {'-'*10}")
    for s in by_unclassified[:top_n]:
        name = s.study_name[:40]
        print(
            f"  {s.study_id:<14s} {name:<40s} {s.unclassified_variables:>12,d}"
            f" {s.total_variables:>10,d}"
        )

    # Top studies by classification rate (only studies with >100 vars)
    with_vars = [s for s in stats_list if s.total_variables > 100]
    by_rate = sorted(with_vars, key=lambda s: -s.classification_rate)
    print(f"\nTop {top_n} studies by classification RATE (>100 vars):")
    print(f"  {'Study':<14s} {'Name':<40s} {'Rate':>8s} {'Classified':>12s}")
    print(f"  {'-'*14} {'-'*40} {'-'*8} {'-'*12}")
    for s in by_rate[:top_n]:
        name = s.study_name[:40]
        print(
            f"  {s.study_id:<14s} {name:<40s} {s.classification_rate:>7.1f}%"
            f" {s.classified_variables:>12,d}"
        )

    # Concept distribution
    all_concepts: dict[str, int] = defaultdict(int)
    for s in stats_list:
        for concept, count in s.concepts.items():
            all_concepts[concept] += count
    sorted_concepts = sorted(all_concepts.items(), key=lambda x: -x[1])

    print(f"\nConcept distribution ({len(sorted_concepts)} concepts):")
    print(f"  {'Concept':<45s} {'Variables':>10s} {'Share':>8s}")
    print(f"  {'-'*45} {'-'*10} {'-'*8}")
    for concept, count in sorted_concepts:
        share = (count / classified_vars * 100) if classified_vars > 0 else 0
        print(f"  {concept:<45s} {count:>10,d} {share:>7.1f}%")

    return stats_list


def save_report(stats_list: list[CoverageStats], path: Path) -> None:
    """Write coverage report to JSON.

    Args:
        stats_list: List of CoverageStats objects.
        path: Output file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([s.to_dict() for s in stats_list], f, indent=2)
    print(f"\nWrote coverage report to {path}")


def main() -> None:
    """Generate and display coverage statistics."""
    parser = argparse.ArgumentParser(description="Generate classification coverage report")
    parser.add_argument("--study", help="Report for this study ID only")
    parser.add_argument("--top", type=int, default=10, help="Number of top-N entries (default: 10)")
    args = parser.parse_args()

    if not CACHE_FILE.exists():
        print(f"ERROR: No parsed tables found at {CACHE_FILE}", file=sys.stderr)
        print("Run parse_var_reports.py first.", file=sys.stderr)
        sys.exit(1)

    if not CLASSIFICATIONS_FILE.exists():
        print(f"ERROR: No classifications found at {CLASSIFICATIONS_FILE}", file=sys.stderr)
        print("Run classify.py first.", file=sys.stderr)
        sys.exit(1)

    tables = load_cache(CACHE_FILE)
    classifications = load_classifications(CLASSIFICATIONS_FILE)

    stats_list = generate_report(tables, classifications, args.study, args.top)
    save_report(stats_list, COVERAGE_FILE)


if __name__ == "__main__":
    main()
