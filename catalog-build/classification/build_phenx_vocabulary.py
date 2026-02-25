#!/usr/bin/env python3
"""Build PhenX concept vocabulary from protocol metadata and variable cross-reference.

Reads:
- source/phenx/protocol_id_name.xls — protocol IDs and human-readable names
- source/phenx/Variable_cross_reference.xlsx — maps PhenX variables to dbGaP phv IDs

Produces: output/phenx-concept-vocabulary.json

Only includes protocols that have at least one dbGaP mapping (i.e., appear in
Variable_cross_reference.xlsx).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PHENX_DIR = Path(__file__).parent / "source" / "phenx"
OUTPUT_DIR = Path(__file__).parent / "output"
PROTOCOL_ID_NAME_PATH = PHENX_DIR / "protocol_id_name.xls"
VARIABLE_XREF_PATH = PHENX_DIR / "Variable_cross_reference.xlsx"
OUTPUT_PATH = OUTPUT_DIR / "phenx-concept-vocabulary.json"


def slugify(name: str) -> str:
    """Convert a protocol name to a concept_id slug.

    Args:
        name: Human-readable protocol name (e.g., "Blood Pressure").

    Returns:
        Lowercase slug with underscores (e.g., "blood_pressure").
    """
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def load_protocol_names(path: Path) -> dict[int, str]:
    """Load protocol_id → name mapping from the XLS file.

    Args:
        path: Path to protocol_id_name.xls.

    Returns:
        Dict mapping protocol_id (int) to protocol name (str).
    """
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)
    result = {}
    for i in range(1, ws.nrows):
        row = ws.row_values(i)
        pid = int(row[0])
        name = str(row[1]).strip()
        if name:
            result[pid] = name
    return result


def load_mapped_protocols(path: Path) -> dict[str, dict]:
    """Load protocol stats from Variable_cross_reference.xlsx.

    Args:
        path: Path to Variable_cross_reference.xlsx.

    Returns:
        Dict keyed by protocol name with counts of mapped phv IDs and studies.
    """
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb.active

    protocols: dict[str, dict] = {}
    seen_rows: set[tuple] = set()

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        protocol_name = row[2]
        phv_id = row[5]
        study_id = row[6]

        if not protocol_name or not phv_id:
            continue
        protocol_name = str(protocol_name).strip()
        phv_id = str(phv_id).strip()

        # Deduplicate rows (the XLSX has duplicates)
        row_key = (protocol_name, phv_id)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        if protocol_name not in protocols:
            protocols[protocol_name] = {
                "phv_count": 0,
                "studies": set(),
            }
        protocols[protocol_name]["phv_count"] += 1
        if study_id:
            # Extract base study ID (phs######)
            sid = str(study_id).strip().split(".")[0]
            protocols[protocol_name]["studies"].add(sid)

    wb.close()
    return protocols


def main() -> None:
    """Build PhenX concept vocabulary."""
    if not PROTOCOL_ID_NAME_PATH.exists():
        print(f"Error: {PROTOCOL_ID_NAME_PATH} not found", file=sys.stderr)
        sys.exit(1)
    if not VARIABLE_XREF_PATH.exists():
        print(f"Error: {VARIABLE_XREF_PATH} not found", file=sys.stderr)
        sys.exit(1)

    # Load protocol names
    id_to_name = load_protocol_names(PROTOCOL_ID_NAME_PATH)
    print(f"Loaded {len(id_to_name)} protocol names")

    # Load mapped protocols (only those with dbGaP mappings)
    mapped = load_mapped_protocols(VARIABLE_XREF_PATH)
    print(f"Found {len(mapped)} protocols with dbGaP mappings")

    # Build vocabulary entries
    vocabulary = []
    for name, stats in sorted(mapped.items()):
        if name == "#N/A":
            continue
        concept_id = f"phenx:{slugify(name)}"
        entry = {
            "concept_id": concept_id,
            "name": name,
            "description": f"PhenX protocol: {name}",
            "dbgap_variable_count": stats["phv_count"],
            "dbgap_study_count": len(stats["studies"]),
            "namespace": "phenx",
        }
        vocabulary.append(entry)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(vocabulary, f, indent=2)

    print(f"Wrote {len(vocabulary)} PhenX concepts to {OUTPUT_PATH}")
    print(f"  Total mapped phv IDs: {sum(v['dbgap_variable_count'] for v in vocabulary)}")


if __name__ == "__main__":
    main()
