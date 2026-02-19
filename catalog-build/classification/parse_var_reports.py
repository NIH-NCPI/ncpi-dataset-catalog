"""Parse dbGaP var_report.xml files to extract table metadata and variable lists.

Usage:
    python parse_var_reports.py                    # Parse all studies
    python parse_var_reports.py --study phs000007  # Parse one study
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from lxml import etree

from models import ParsedTable

# Paths relative to this script
SCRIPT_DIR = Path(__file__).parent
SOURCE_DIR = SCRIPT_DIR.parent / "source" / "dbgap-variables"
OUTPUT_DIR = SCRIPT_DIR / "output"
CACHE_FILE = OUTPUT_DIR / "parsed-tables.json"


def parse_var_report(xml_path: Path, dir_study_id: str) -> ParsedTable:
    """Parse a single var_report.xml file into a ParsedTable.

    Args:
        xml_path: Path to the XML file.
        dir_study_id: The study directory name (e.g. "phs000007").

    Returns:
        A ParsedTable with deduplicated variable names.
    """
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    # Extract study_id from XML attribute, strip version suffix
    raw_study_id = root.get("study_id", "")
    study_id = raw_study_id.split(".")[0] if raw_study_id else dir_study_id

    dataset_id = root.get("dataset_id", "")
    table_name = root.get("name", "")
    study_name = root.get("study_name", "")

    desc_elem = root.find("description")
    description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

    # Collect unique variables with descriptions and IDs
    # (deduplicates consent-group variants like .c1, .c2)
    seen: dict[str, dict[str, str]] = {}  # name -> {description, id}
    for var_elem in root.findall("variable"):
        name = var_elem.get("var_name")
        if name and name not in seen:
            desc_text = ""
            desc_el = var_elem.find("description")
            if desc_el is not None and desc_el.text:
                # Strip the trailing "[TableName. Visit N]" context tag
                raw = desc_el.text.strip()
                bracket = raw.rfind(" [")
                desc_text = raw[:bracket] if bracket > 0 else raw
            phv_id = var_elem.get("id", "")
            seen[name] = {"description": desc_text, "id": phv_id}

    variables = [
        {"name": name, "description": seen[name]["description"], "id": seen[name]["id"]}
        for name in sorted(seen)
    ]

    rel_path = str(xml_path.relative_to(SOURCE_DIR.parent.parent))

    return ParsedTable(
        study_id=study_id,
        dataset_id=dataset_id,
        table_name=table_name,
        study_name=study_name,
        description=description,
        variables=variables,
        variable_count=len(variables),
        file_path=rel_path,
    )


def parse_study(study_dir: Path) -> list[ParsedTable]:
    """Parse all var_report.xml files in a study directory.

    Args:
        study_dir: Path to a study directory (e.g. .../dbgap-variables/phs000007/).

    Returns:
        List of ParsedTable objects.
    """
    dir_study_id = study_dir.name
    xml_files = sorted(study_dir.glob("*.var_report.xml"))
    tables = []
    for xml_path in xml_files:
        try:
            table = parse_var_report(xml_path, dir_study_id)
            tables.append(table)
        except Exception as e:
            print(f"  WARNING: Failed to parse {xml_path.name}: {e}", file=sys.stderr)
    return tables


def parse_all_studies(study_filter: str | None = None) -> list[ParsedTable]:
    """Parse var_report.xml files for all (or one) study.

    Args:
        study_filter: If set, only parse this study ID.

    Returns:
        List of all ParsedTable objects.
    """
    if not SOURCE_DIR.is_dir():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}", file=sys.stderr)
        sys.exit(1)

    study_dirs = sorted(
        d for d in SOURCE_DIR.iterdir()
        if d.is_dir() and d.name.startswith("phs")
    )

    if study_filter:
        study_dirs = [d for d in study_dirs if d.name == study_filter]
        if not study_dirs:
            print(f"ERROR: Study directory not found: {study_filter}", file=sys.stderr)
            sys.exit(1)

    all_tables: list[ParsedTable] = []
    start = time.time()

    for i, study_dir in enumerate(study_dirs, 1):
        tables = parse_study(study_dir)
        all_tables.extend(tables)
        if i % 50 == 0 or i == len(study_dirs):
            elapsed = time.time() - start
            print(f"  Parsed {i}/{len(study_dirs)} studies ({len(all_tables)} tables, {elapsed:.1f}s)")

    return all_tables


def save_cache(tables: list[ParsedTable], path: Path) -> None:
    """Write parsed tables to JSON cache.

    Args:
        tables: List of ParsedTable objects.
        path: Output file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([t.to_dict() for t in tables], f, indent=2)
    print(f"Wrote {len(tables)} tables to {path}")


def load_cache(path: Path) -> list[ParsedTable]:
    """Load parsed tables from JSON cache.

    Args:
        path: Path to the cached JSON file.

    Returns:
        List of ParsedTable objects.
    """
    with open(path) as f:
        data = json.load(f)
    return [ParsedTable.from_dict(d) for d in data]


def main() -> None:
    """Parse var_report.xml files and write results to cache."""
    parser = argparse.ArgumentParser(description="Parse dbGaP var_report.xml files")
    parser.add_argument("--study", help="Parse only this study ID (e.g. phs000007)")
    args = parser.parse_args()

    print(f"Source: {SOURCE_DIR}")
    print(f"Parsing {'study ' + args.study if args.study else 'all studies'}...")

    tables = parse_all_studies(args.study)

    total_vars = sum(t.variable_count for t in tables)
    studies = {t.study_id for t in tables}
    print(f"\nParsed {len(tables)} tables across {len(studies)} studies")
    print(f"Total unique variables: {total_vars:,}")

    save_cache(tables, CACHE_FILE)


if __name__ == "__main__":
    main()
