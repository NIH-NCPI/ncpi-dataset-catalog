#!/usr/bin/env python3
"""Merge PhenX ground-truth variable mappings into v4 classification output.

Reads Variable_cross_reference.xlsx to get phv_id → PhenX protocol mappings,
then for each v4 study JSON:
- If a variable has null concept_id and PhenX has a mapping → set phenx concept
- If a variable already has a topmed: concept_id → skip (more specific)

This adds PhenX coverage without any LLM calls.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PHENX_DIR = Path(__file__).parent / "source" / "phenx"
OUTPUT_DIR = Path(__file__).parent / "output"
V4_DIR = OUTPUT_DIR / "llm-concepts-v4"
VARIABLE_XREF_PATH = PHENX_DIR / "Variable_cross_reference.xlsx"


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


def load_phenx_phv_map(path: Path) -> dict[str, str]:
    """Build phv_base_id → phenx concept_id mapping from Variable_cross_reference.xlsx.

    Args:
        path: Path to Variable_cross_reference.xlsx.

    Returns:
        Dict mapping phv base ID (e.g., "phv00079232") to phenx concept_id.
    """
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb.active

    phv_map: dict[str, str] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        protocol_name = row[2]
        phv_id = row[5]

        if not protocol_name or not phv_id:
            continue

        protocol_name = str(protocol_name).strip()
        if protocol_name == "#N/A":
            continue

        phv_str = str(phv_id).strip()
        # Extract base phv ID (strip version suffix)
        phv_base = phv_str.split(".")[0]
        concept_id = f"phenx:{slugify(protocol_name)}"

        # First mapping wins (avoid duplicates overwriting)
        if phv_base not in phv_map:
            phv_map[phv_base] = concept_id

    wb.close()
    return phv_map


def inject_phenx_into_study(
    data: dict, phv_map: dict[str, str]
) -> dict[str, int]:
    """Inject PhenX mappings into a single study's v4 JSON (in-place).

    Args:
        data: Parsed v4 study JSON (modified in-place).
        phv_map: phv base ID → phenx concept_id mapping.

    Returns:
        Stats dict with injection counts.
    """
    stats = {"injected": 0, "skipped_has_topmed": 0}

    for table in data.get("tables", []):
        for var in table.get("variables", []):
            phv_id = var.get("id", "")
            phv_base = phv_id.split(".")[0] if phv_id else ""

            if phv_base not in phv_map:
                continue

            # If variable already has a topmed concept, keep it (more specific)
            existing = var.get("concept_id")
            if existing and existing.startswith("topmed:"):
                stats["skipped_has_topmed"] += 1
                continue

            # Inject PhenX mapping
            var["concept_id"] = phv_map[phv_base]
            var["cui"] = None  # PhenX protocols don't have CUIs
            var["confidence"] = "high"
            var["source"] = "phenx_ground_truth"
            stats["injected"] += 1

    return stats


def main() -> None:
    """Inject PhenX ground-truth mappings into all v4 study files."""
    if not V4_DIR.exists():
        print(f"Error: v4 directory not found: {V4_DIR}", file=sys.stderr)
        print("Run namespace_v3_output.py first.", file=sys.stderr)
        sys.exit(1)

    print("Loading PhenX variable cross-reference...")
    phv_map = load_phenx_phv_map(VARIABLE_XREF_PATH)
    print(f"  {len(phv_map)} unique phv → phenx mappings")

    files = sorted(V4_DIR.glob("phs*.json"))
    print(f"Processing {len(files)} v4 study files...")

    totals = {"injected": 0, "skipped_has_topmed": 0, "studies_with_phenx": 0}
    for path in files:
        with open(path) as f:
            data = json.load(f)

        stats = inject_phenx_into_study(data, phv_map)
        if stats["injected"] > 0:
            totals["studies_with_phenx"] += 1

        totals["injected"] += stats["injected"]
        totals["skipped_has_topmed"] += stats["skipped_has_topmed"]

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    print(f"Done.")
    print(f"  PhenX variables injected: {totals['injected']}")
    print(f"  Skipped (had topmed concept): {totals['skipped_has_topmed']}")
    print(f"  Studies with PhenX mappings: {totals['studies_with_phenx']}")


if __name__ == "__main__":
    main()
