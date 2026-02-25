#!/usr/bin/env python3
"""Transform v3 classification output to v4 format with namespace prefixes and CUI.

Reads per-study JSON from llm-concepts-v3/, adds:
- ``topmed:`` namespace prefix to each concept_id
- CUI from concept-vocabulary.json
- Writes to llm-concepts-v4/

Null concept_ids remain null (no prefix, no CUI).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
V3_DIR = OUTPUT_DIR / "llm-concepts-v3"
V4_DIR = OUTPUT_DIR / "llm-concepts-v4"
VOCAB_PATH = OUTPUT_DIR / "concept-vocabulary.json"


def load_cui_map(vocab_path: Path) -> dict[str, str | None]:
    """Build concept_id → CUI lookup from concept-vocabulary.json.

    Args:
        vocab_path: Path to the vocabulary JSON file.

    Returns:
        Dict mapping concept_id to CUI (or None).
    """
    with open(vocab_path) as f:
        vocab = json.load(f)
    return {entry["concept_id"]: entry.get("cui") for entry in vocab}


def namespace_variable(
    var: dict, cui_map: dict[str, str | None]
) -> dict:
    """Add namespace prefix and CUI to a single variable dict.

    Args:
        var: Variable dict from v3 output.
        cui_map: concept_id → CUI lookup.

    Returns:
        New variable dict with concept_id prefixed and cui added.
    """
    concept_id = var.get("concept_id")
    if concept_id:
        namespaced = f"topmed:{concept_id}"
        cui = cui_map.get(concept_id)
    else:
        namespaced = None
        cui = None
    return {
        "name": var["name"],
        "id": var["id"],
        "description": var.get("description", ""),
        "concept_id": namespaced,
        "cui": cui,
        "confidence": var.get("confidence", "high"),
        "source": var.get("source", "llm"),
    }


def transform_study(
    data: dict, cui_map: dict[str, str | None]
) -> dict:
    """Transform a full study JSON from v3 to v4 format.

    Args:
        data: Parsed v3 study JSON.
        cui_map: concept_id → CUI lookup.

    Returns:
        v4 study dict with namespaced concept_ids and CUIs.
    """
    tables = []
    for table in data.get("tables", []):
        variables = [
            namespace_variable(v, cui_map) for v in table.get("variables", [])
        ]
        tables.append({
            "tableName": table.get("tableName", ""),
            "datasetId": table.get("datasetId", ""),
            "description": table.get("description"),
            "variables": variables,
        })
    return {
        "studyId": data.get("studyId", ""),
        "studyName": data.get("studyName", ""),
        "tables": tables,
    }


def main() -> None:
    """Transform all v3 study files to v4 format."""
    if not V3_DIR.exists():
        print(f"Error: v3 directory not found: {V3_DIR}", file=sys.stderr)
        sys.exit(1)

    cui_map = load_cui_map(VOCAB_PATH)
    print(f"Loaded CUI map: {len(cui_map)} concepts")

    V4_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(V3_DIR.glob("phs*.json"))
    print(f"Transforming {len(files)} study files...")

    stats = {"total": 0, "with_concept": 0, "with_cui": 0}
    for path in files:
        with open(path) as f:
            data = json.load(f)
        result = transform_study(data, cui_map)
        out_path = V4_DIR / path.name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        # Count stats
        for table in result["tables"]:
            for var in table["variables"]:
                stats["total"] += 1
                if var["concept_id"]:
                    stats["with_concept"] += 1
                if var["cui"]:
                    stats["with_cui"] += 1

    print(f"Done. Wrote {len(files)} files to {V4_DIR}")
    print(f"  Variables: {stats['total']}")
    print(f"  With concept: {stats['with_concept']}")
    print(f"  With CUI: {stats['with_cui']}")


if __name__ == "__main__":
    main()
