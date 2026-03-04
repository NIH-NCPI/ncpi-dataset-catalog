"""Build focus term → MeSH category mapping and ISA hierarchy.

Looks up each focus term in the MeSH API to get tree numbers,
then groups by top-level MeSH disease category.

Also computes parent→child ISA edges from MeSH tree numbers so that
searching a parent focus term (e.g. "Pancreatic Neoplasms") returns
studies tagged with any descendant term.

Output: focus_categories.json, focus_isa.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .index import get_index

MESH_LOOKUP_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
MESH_DESCRIPTOR_URL = "https://id.nlm.nih.gov/mesh"

# Map MeSH tree prefixes to consolidated category names.
# Multiple tree codes can map to the same category.
TREE_TO_CATEGORY = {
    # Diseases (C branch)
    "C01": "Infections",
    "C02": "Infections",
    "C03": "Infections",
    "C04": "Neoplasms",
    "C05": "Musculoskeletal Diseases",
    "C06": "Digestive System Diseases",
    "C07": "Stomatognathic Diseases",
    "C08": "Respiratory Tract Diseases",
    "C09": "Otorhinolaryngologic Diseases",
    "C10": "Nervous System Diseases",
    "C11": "Eye Diseases",
    "C12": "Urogenital Diseases",
    "C13": "Urogenital Diseases",
    "C14": "Cardiovascular Diseases",
    "C15": "Hemic and Lymphatic Diseases",
    "C16": "Congenital and Hereditary Diseases",
    "C17": "Skin and Connective Tissue Diseases",
    "C18": "Nutritional and Metabolic Diseases",
    "C19": "Endocrine System Diseases",
    "C20": "Immune System Diseases",
    "C21": "Environmental Disorders",
    "C22": "Animal Diseases",
    "C23": "Pathological Conditions and Signs",
    "C24": "Occupational Diseases",
    "C25": "Chemically-Induced Disorders",
    "C26": "Wounds and Injuries",
    # Mental/behavioral (F branch)
    "F01": "Mental and Behavioral",
    "F03": "Mental and Behavioral",
    # Non-disease trees commonly used as study focus
    "B01": "Organisms",
    "B02": "Organisms",
    "B03": "Organisms",
    "B04": "Organisms",
    "E01": "Medical Techniques",
    "E02": "Medical Techniques",
    "E05": "Medical Techniques",
    "G01": "Biological Phenomena",
    "G02": "Biological Phenomena",
    "G04": "Biological Phenomena",
    "G05": "Genetics",
    "G06": "Biological Phenomena",
    "G07": "Biological Phenomena",
    "G08": "Biological Phenomena",
    "G16": "Biological Phenomena",
    "H02": "Health Occupations",
    "I01": "Social Sciences",
    "L01": "Information Science",
    "M01": "Populations",
    "N01": "Population Characteristics",
    "N05": "Health Care",
    "N06": "Environment and Public Health",
    "Z01": "Geographic Locations",
}

OUTPUT_PATH = Path(__file__).parent / "focus_categories.json"
ISA_OUTPUT_PATH = Path(__file__).parent / "focus_isa.json"


async def lookup_descriptor_uid(
    client: httpx.AsyncClient, label: str
) -> str | None:
    """Look up a MeSH descriptor UID by label."""
    resp = await client.get(
        MESH_LOOKUP_URL,
        params={"label": label, "match": "exact", "limit": 1},
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data:
        return None
    resource = data[0].get("resource", "")
    uid = resource.split("/")[-1] if resource else None
    return uid


async def lookup_tree_numbers(
    client: httpx.AsyncClient, uid: str
) -> list[str]:
    """Get tree numbers for a MeSH descriptor UID."""
    resp = await client.get(f"{MESH_DESCRIPTOR_URL}/{uid}.json")
    if resp.status_code != 200:
        return []
    data = resp.json()
    tree_nums = data.get("treeNumber", [])
    if isinstance(tree_nums, str):
        tree_nums = [tree_nums]
    codes = []
    for tn in tree_nums:
        if isinstance(tn, dict):
            tn = tn.get("@id", "")
        code = tn.split("/")[-1] if "/" in tn else tn
        codes.append(code)
    return codes


async def process_term(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    term: str,
    study_count: int,
) -> dict:
    """Look up one focus term and return its category info."""
    async with sem:
        uid = await lookup_descriptor_uid(client, term)
        if not uid:
            return {
                "term": term,
                "study_count": study_count,
                "uid": None,
                "tree_numbers": [],
                "categories": [],
            }

        tree_numbers = await lookup_tree_numbers(client, uid)
        categories = set()
        for code in tree_numbers:
            top = code[:3]
            cat_name = TREE_TO_CATEGORY.get(top)
            if cat_name:
                categories.add(cat_name)
        return {
            "term": term,
            "study_count": study_count,
            "uid": uid,
            "tree_numbers": tree_numbers,
            "categories": sorted(categories),
        }


def _compute_isa_edges(results: list[dict]) -> list[dict]:
    """Derive child→parent ISA edges from MeSH tree numbers.

    For each focus term with tree numbers, walk up the tree to find
    the nearest ancestor that is also a catalog focus term.  Handles
    MeSH polyhierarchy (multiple tree numbers per term).

    Args:
        results: Output of ``process_term`` — each has ``term`` and ``tree_numbers``.

    Returns:
        List of ``{"child": ..., "parent": ...}`` edges (same format as concept-isa.json).
    """
    # Build reverse map: tree_number → focus term (only for terms in our catalog)
    tree_to_term: dict[str, str] = {}
    for r in results:
        for tn in r["tree_numbers"]:
            tree_to_term[tn] = r["term"]

    edges: set[tuple[str, str]] = set()
    for r in results:
        child_term = r["term"]
        for tn in r["tree_numbers"]:
            # Walk up the tree: A.B.C.D → A.B.C → A.B → A
            parts = tn.split(".")
            for depth in range(len(parts) - 1, 0, -1):
                ancestor_tn = ".".join(parts[:depth])
                ancestor_term = tree_to_term.get(ancestor_tn)
                if ancestor_term and ancestor_term != child_term:
                    edges.add((child_term, ancestor_term))
                    break  # nearest ancestor only

    return sorted(
        [{"child": c, "parent": p} for c, p in edges],
        key=lambda e: (e["parent"], e["child"]),
    )


async def build_categories() -> None:
    """Build the focus category mapping and ISA hierarchy."""
    index = get_index()
    focus_values = index.list_facet_values("focus")
    print(f"Looking up {len(focus_values)} focus terms in MeSH...")

    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [
            process_term(sem, client, m.value, m.study_count)
            for m in focus_values
        ]
        results = await asyncio.gather(*tasks)

    # Build category → terms mapping (consolidated by category name)
    category_terms: dict[str, list[dict]] = {}
    unmapped = []
    for r in results:
        if not r["categories"]:
            unmapped.append(r)
            continue
        for cat_name in r["categories"]:
            if cat_name not in category_terms:
                category_terms[cat_name] = []
            category_terms[cat_name].append({
                "term": r["term"],
                "study_count": r["study_count"],
            })

    # Deduplicate terms within categories (a term may appear via multiple tree codes)
    for cat_name in category_terms:
        seen = set()
        deduped = []
        for entry in category_terms[cat_name]:
            if entry["term"] not in seen:
                seen.add(entry["term"])
                deduped.append(entry)
        category_terms[cat_name] = deduped

    # Add unmapped terms to "Other" category
    if unmapped:
        category_terms["Other"] = [
            {"term": u["term"], "study_count": u["study_count"]}
            for u in unmapped
        ]

    # Sort categories and terms within each
    output = {
        "categories": {
            k: sorted(v, key=lambda x: -x["study_count"])
            for k, v in sorted(category_terms.items())
        },
        "stats": {
            "total_terms": len(focus_values),
            "mapped_terms": len(focus_values) - len(unmapped),
            "unmapped_terms": len(unmapped),
            "category_count": len(category_terms),
        },
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"  {output['stats']['mapped_terms']} mapped, "
          f"{output['stats']['unmapped_terms']} unmapped → Other")
    print(f"  {output['stats']['category_count']} categories total")

    print("\nCategories:")
    for key, terms in sorted(output["categories"].items()):
        print(f"  {key}: {len(terms)} terms")

    # Build and write ISA edges from MeSH tree numbers
    isa_edges = _compute_isa_edges(results)
    ISA_OUTPUT_PATH.write_text(json.dumps(isa_edges, indent=2))
    print(f"\nWrote {ISA_OUTPUT_PATH}")
    print(f"  {len(isa_edges)} ISA edges")


def main() -> None:
    """CLI entry point."""
    _backend_dir = Path(__file__).parent.parent
    load_dotenv(_backend_dir / ".env")
    asyncio.run(build_categories())


if __name__ == "__main__":
    main()
