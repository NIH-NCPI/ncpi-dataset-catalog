#!/usr/bin/env python3
"""Dump the full concept hierarchy as a tree with variable counts."""

import json
import sys
from collections import defaultdict
from pathlib import Path

OUTPUT = Path(__file__).parent / "output"
STUDY_DIR = OUTPUT / "llm-concepts-v4"


def main() -> None:
    # Load hierarchy data
    isa = json.loads((OUTPUT / "concept-isa.json").read_text())
    cats = json.loads((OUTPUT / "ncpi-categories.json").read_text())
    vocab = json.loads((OUTPUT / "concept-vocabulary.json").read_text())

    # Build name lookup from vocab
    name_of: dict[str, str] = {}
    for entry in vocab:
        name_of[entry["concept_id"]] = entry["name"]
    for cat in cats:
        name_of[cat["concept_id"]] = cat["name"]

    # Build parent→children adjacency
    children_of: dict[str, list[str]] = defaultdict(list)
    for edge in isa:
        children_of[edge["parent"]].append(edge["child"])
    for v in children_of.values():
        v.sort()

    # Count variables per concept_id across all study files
    var_count: dict[str, int] = defaultdict(int)
    for study_file in sorted(STUDY_DIR.glob("*.json")):
        study = json.loads(study_file.read_text())
        for table in study.get("tables", []):
            for var in table.get("variables", []):
                cid = var.get("concept_id")
                if cid:
                    var_count[cid] += 1

    # Compute roll-up counts (sum of self + all descendants)
    def rollup(concept_id: str) -> int:
        total = var_count.get(concept_id, 0)
        for child in children_of.get(concept_id, []):
            total += rollup(child)
        return total

    # Print tree
    total_vars = sum(var_count.values())
    total_concepts = len({cid for cid in var_count if var_count[cid] > 0})
    print(f"# NCPI Concept Hierarchy ({total_concepts} concepts, "
          f"{total_vars:,} classified variables)\n")

    for cat in cats:
        cat_id = cat["concept_id"]
        cat_total = rollup(cat_id)
        if cat_total == 0 and not children_of.get(cat_id):
            continue
        print(f"## {cat['name']} (`{cat_id}`) — {cat_total:,} vars\n")

        for child in children_of.get(cat_id, []):
            child_name = name_of.get(child, child)
            child_rollup = rollup(child)
            child_own = var_count.get(child, 0)
            grandchildren = children_of.get(child, [])

            if grandchildren:
                print(f"- **{child_name}** (`{child}`) — "
                      f"{child_rollup:,} vars")
                for gc in grandchildren:
                    gc_name = name_of.get(gc, gc)
                    gc_count = var_count.get(gc, 0)
                    gc_children = children_of.get(gc, [])
                    if gc_children:
                        # 3rd level with its own children (archetypes)
                        gc_rollup = rollup(gc)
                        gc_own = var_count.get(gc, 0)
                        remaining = f" (+{gc_own} untyped)" if gc_own else ""
                        print(f"  - **{gc_name}** (`{gc}`) — "
                              f"{gc_rollup:,} vars{remaining}")
                        for ggc in gc_children:
                            ggc_name = name_of.get(ggc, ggc)
                            ggc_count = var_count.get(ggc, 0)
                            if ggc_count:
                                print(f"    - {ggc_name} — {ggc_count:,}")
                            else:
                                print(f"    - {ggc_name}")
                    else:
                        if gc_count:
                            print(f"  - {gc_name} — {gc_count:,}")
                        else:
                            print(f"  - {gc_name}")
            else:
                if child_own:
                    print(f"- {child_name} (`{child}`) — {child_own:,} vars")
                else:
                    print(f"- {child_name} (`{child}`)")

        print()


if __name__ == "__main__":
    main()
