"""Apply synonym mappings to per-study concept classification files.

Reads the synonym map from reorganize_concepts.py and rewrites concept
names in per-study JSON files to use canonical forms.

Usage:
    python apply_synonyms.py                    # Apply to all studies
    python apply_synonyms.py --study phs000007  # One study
    python apply_synonyms.py --dry-run          # Show what would change
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
V1_CONCEPT_DIR = SCRIPT_DIR / "output" / "llm-concepts"
V2_OUTPUT_DIR = SCRIPT_DIR / "output" / "v2"
V2_CONCEPT_DIR = V2_OUTPUT_DIR / "llm-concepts"
SYNONYM_MAP_PATH = V2_OUTPUT_DIR / "synonym-map.json"


def load_synonym_map(path: Path) -> dict[str, str]:
    """Load the synonym map JSON.

    Args:
        path: Path to synonym-map.json.

    Returns:
        Dict mapping old concept names to canonical names.
    """
    with open(path) as f:
        data = json.load(f)
    return data.get("mapping", {})


def apply_to_study(
    input_path: Path,
    output_path: Path,
    synonym_map: dict[str, str],
    dry_run: bool = False,
) -> tuple[int, int]:
    """Apply synonym map to one study's JSON file.

    Args:
        input_path: Path to the v1 per-study JSON.
        output_path: Path to write the v2 per-study JSON.
        synonym_map: Old name -> canonical name mapping.
        dry_run: If True, count changes but don't write.

    Returns:
        Tuple of (total variables, variables renamed).
    """
    with open(input_path) as f:
        data = json.load(f)

    total_vars = 0
    renamed_vars = 0

    for table in data.get("tables", []):
        for var in table.get("variables", []):
            total_vars += 1
            old_concept = var.get("concept", "")
            if old_concept in synonym_map:
                var["concept"] = synonym_map[old_concept]
                renamed_vars += 1

        # Rebuild table-level concepts list
        table["concepts"] = sorted({
            v["concept"] for v in table.get("variables", [])
        })

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    return total_vars, renamed_vars


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Apply synonym mappings to per-study concept files"
    )
    parser.add_argument(
        "--study",
        help="Only process this study ID (e.g. phs000007)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    args = parser.parse_args()

    if not SYNONYM_MAP_PATH.exists():
        print(
            f"ERROR: Synonym map not found: {SYNONYM_MAP_PATH}",
            file=sys.stderr,
        )
        print("Run reorganize_concepts.py first.", file=sys.stderr)
        sys.exit(1)

    synonym_map = load_synonym_map(SYNONYM_MAP_PATH)
    print(
        f"Loaded synonym map: {len(synonym_map)} mappings",
        file=sys.stderr,
    )

    if not synonym_map:
        print("No synonyms to apply.", file=sys.stderr)
        return

    # Find input files
    if args.study:
        input_files = [V1_CONCEPT_DIR / f"{args.study}.json"]
        if not input_files[0].exists():
            print(
                f"ERROR: Study file not found: {input_files[0]}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        input_files = sorted(V1_CONCEPT_DIR.glob("phs*.json"))

    print(
        f"Processing {len(input_files)} study files...",
        file=sys.stderr,
    )

    total_vars = 0
    total_renamed = 0
    files_changed = 0

    for input_path in input_files:
        output_path = V2_CONCEPT_DIR / input_path.name
        n_vars, n_renamed = apply_to_study(
            input_path, output_path, synonym_map, args.dry_run
        )
        total_vars += n_vars
        total_renamed += n_renamed
        if n_renamed > 0:
            files_changed += 1

    # Copy unchanged files too (so v2 dir is complete)
    if not args.dry_run:
        for input_path in input_files:
            output_path = V2_CONCEPT_DIR / input_path.name
            if not output_path.exists():
                shutil.copy2(input_path, output_path)

    action = "Would rename" if args.dry_run else "Renamed"
    print(
        f"\n{action} {total_renamed:,} / {total_vars:,} variables "
        f"across {files_changed} / {len(input_files)} files.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
