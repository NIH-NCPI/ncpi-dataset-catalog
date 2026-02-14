"""Classify dbGaP dataset tables into concepts using per-study rule files.

Usage:
    python classify.py                              # Run all studies
    python classify.py --study phs000007            # Run one study
    python classify.py --study phs000007 --dry-run  # Show matches without writing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from models import Classification, ParsedTable, Rule, RuleFile
from parse_var_reports import CACHE_FILE, load_cache, parse_all_studies, save_cache

SCRIPT_DIR = Path(__file__).parent
RULES_DIR = SCRIPT_DIR / "rules"
OUTPUT_DIR = SCRIPT_DIR / "output"
CLASSIFICATIONS_FILE = OUTPUT_DIR / "classifications.json"


def load_rules(study_id: str) -> tuple[list[Rule], list[Rule]]:
    """Load study-specific and default rules.

    Args:
        study_id: The study to load rules for.

    Returns:
        Tuple of (study_rules, default_rules).
    """
    study_rules: list[Rule] = []
    default_rules: list[Rule] = []

    study_path = RULES_DIR / f"{study_id}.json"
    if study_path.exists():
        rf = RuleFile.load(study_path)
        study_rules = rf.rules

    default_path = RULES_DIR / "_default.json"
    if default_path.exists():
        rf = RuleFile.load(default_path)
        default_rules = rf.rules

    return study_rules, default_rules


def match_table(table: ParsedTable, rules: list[Rule]) -> Rule | None:
    """Try to match a table against a list of rules (first match wins).

    Args:
        table: The parsed table to match.
        rules: Ordered list of rules to try.

    Returns:
        The first matching Rule, or None.
    """
    for rule in rules:
        if rule.match_field == "tableName":
            value = table.table_name
        elif rule.match_field == "description":
            value = table.description
        else:
            continue

        if re.search(rule.pattern, value):
            return rule

    return None


def classify_tables(
    tables: list[ParsedTable],
    study_filter: str | None = None,
    dry_run: bool = False,
) -> list[Classification]:
    """Classify tables into concepts using rule files.

    Args:
        tables: All parsed tables.
        study_filter: If set, only classify this study.
        dry_run: If True, print matches but don't write output.

    Returns:
        List of Classification results.
    """
    # Group tables by study_id
    by_study: dict[str, list[ParsedTable]] = defaultdict(list)
    for t in tables:
        by_study[t.study_id].append(t)

    study_ids = sorted(by_study.keys())
    if study_filter:
        study_ids = [s for s in study_ids if s == study_filter]

    all_classifications: list[Classification] = []
    total_unclassified_vars = 0
    total_unclassified_tables = 0

    for study_id in study_ids:
        study_tables = by_study[study_id]
        study_rules, default_rules = load_rules(study_id)

        classified_vars = 0
        unclassified_tables: list[ParsedTable] = []

        for table in study_tables:
            # Study-specific rules first, then defaults
            rule = match_table(table, study_rules)
            source_prefix = study_id
            if rule is None:
                rule = match_table(table, default_rules)
                source_prefix = "_default"

            if rule:
                classification = Classification(
                    study_id=study_id,
                    dataset_id=table.dataset_id,
                    table_name=table.table_name,
                    concept=rule.concept,
                    domain=rule.domain,
                    phase=1,
                    rule_source=f"{source_prefix}:{rule.match_field}:{rule.pattern}",
                    variable_count=table.variable_count,
                    variables=table.variables,
                )
                all_classifications.append(classification)
                classified_vars += table.variable_count

                if dry_run:
                    print(
                        f"  MATCH  {table.table_name:40s} -> {rule.concept}"
                        f"  ({table.variable_count} vars)"
                    )
            else:
                unclassified_tables.append(table)

        unclassified_vars = sum(t.variable_count for t in unclassified_tables)
        total_vars = sum(t.variable_count for t in study_tables)
        total_unclassified_vars += unclassified_vars
        total_unclassified_tables += len(unclassified_tables)

        if dry_run and (study_filter or unclassified_tables):
            study_name = study_tables[0].study_name if study_tables else study_id
            rate = (classified_vars / total_vars * 100) if total_vars > 0 else 0
            print(f"\n{study_id}  {study_name}")
            print(
                f"  Classified: {classified_vars:,} / {total_vars:,} vars ({rate:.1f}%)"
            )
            if unclassified_tables:
                print(f"  Unclassified tables ({len(unclassified_tables)}):")
                for t in sorted(unclassified_tables, key=lambda x: -x.variable_count):
                    desc = t.description if t.description else "(no description)"
                    if len(desc) > 300:
                        desc = desc[:297] + "..."
                    print(f"    {t.table_name:40s} {t.variable_count:6d} vars")
                    print(f"      {desc}")

    return all_classifications


def save_classifications(classifications: list[Classification], path: Path) -> None:
    """Write classifications to JSON.

    Args:
        classifications: List of Classification objects.
        path: Output file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([c.to_dict() for c in classifications], f, indent=2)
    print(f"Wrote {len(classifications)} classifications to {path}")


def main() -> None:
    """Run the classification pipeline."""
    parser = argparse.ArgumentParser(description="Classify dbGaP tables into concepts")
    parser.add_argument("--study", help="Classify only this study ID (e.g. phs000007)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without writing output",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="Re-parse XML files even if cache exists",
    )
    args = parser.parse_args()

    # Load or parse tables
    if CACHE_FILE.exists() and not args.reparse:
        print(f"Loading cached tables from {CACHE_FILE}...")
        tables = load_cache(CACHE_FILE)
        print(f"Loaded {len(tables)} tables")
    else:
        print("Parsing XML files...")
        tables = parse_all_studies()
        save_cache(tables, CACHE_FILE)

    # Classify
    classifications = classify_tables(tables, args.study, args.dry_run)

    if not args.dry_run:
        save_classifications(classifications, CLASSIFICATIONS_FILE)

        # Print summary
        total_vars = sum(c.variable_count for c in classifications)
        all_vars = sum(t.variable_count for t in tables)
        if args.study:
            all_vars = sum(
                t.variable_count for t in tables if t.study_id == args.study
            )
        studies = {c.study_id for c in classifications}
        concepts = {c.concept for c in classifications}
        rate = (total_vars / all_vars * 100) if all_vars > 0 else 0

        print(f"\nClassified {total_vars:,} / {all_vars:,} variables ({rate:.1f}%)")
        print(f"Across {len(studies)} studies, {len(concepts)} concepts")


if __name__ == "__main__":
    main()
