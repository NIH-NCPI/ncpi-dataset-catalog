"""Extract seed concept data from TOPMed harmonized variable documentation.

Reads the 78 harmonized variable JSONs, cross-references component phv IDs
against parsed-tables.json (75K dbGaP variables), and produces:
  - topmed-seed-concepts.json: full seed reference with component variables
  - concept-vocabulary.json: LLM matching vocabulary with example variables
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HARMONIZED_DIR = Path(__file__).parent.parent / (
    "source/harmonization-sources/topmed-harmonized/"
    "harmonized-variable-documentation"
)
PHS_MAPPING_FILE = Path(__file__).parent.parent / (
    "source/harmonization-sources/topmed-harmonized/phs-mapping.tsv"
)
PARSED_TABLES_FILE = Path(__file__).parent / "output/parsed-tables.json"
OUTPUT_DIR = Path(__file__).parent / "output"

# Regex to parse "phs000280.v4.pht004063.v2.phv00204712.v1"
DBGAP_ID_RE = re.compile(
    r"(phs\d+)\.v\d+\.(pht\d+)\.v\d+\.(phv\d+\.v\d+)"
)


def load_phs_mapping():
    """Load phs number -> study name mapping from TSV.

    Returns:
        dict mapping phs accession (e.g. "phs000280") to study name.
    """
    mapping = {}
    with open(PHS_MAPPING_FILE) as f:
        header = True
        for line in f:
            if header:
                header = False
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                phs_num = parts[0]
                study_name = parts[1]
                # Pad phs number to match dbGaP format: "280" -> "phs000280"
                mapping[f"phs{int(phs_num):06d}"] = study_name
    return mapping


def parse_component_variable(var_string):
    """Parse a component_study_variables string into phs/pht/phv parts.

    Args:
        var_string: e.g. "phs000280.v4.pht004063.v2.phv00204712.v1"

    Returns:
        Dict with phs, pht, phv keys, or None if parsing fails.
    """
    m = DBGAP_ID_RE.match(var_string)
    if not m:
        return None
    return {"phs": m.group(1), "pht": m.group(2), "phv": m.group(3)}


def _phv_base(phv_id):
    """Extract the base phv ID without version or participant suffix.

    Args:
        phv_id: e.g. "phv00054139.v1.p1" or "phv00054139.v1"

    Returns:
        Base ID like "phv00054139".
    """
    return phv_id.split(".")[0] if phv_id else ""


def build_phv_lookup(parsed_tables):
    """Build a lookup from phv base ID -> (variable_name, variable_description).

    Harmonized variable JSONs reference specific phv versions (e.g.
    "phv00023194.v3") while parsed-tables.json may have different versions
    (e.g. "phv00023194.v7.p16"). We match on the base phv ID only since
    the variable identity is stable across versions.

    Args:
        parsed_tables: Parsed content of parsed-tables.json.

    Returns:
        Dict mapping base phv ID to (name, description) tuple.
    """
    lookup = {}
    for table in parsed_tables:
        for var in table.get("variables", []):
            raw_id = var.get("id", "")
            base = _phv_base(raw_id)
            if base.startswith("phv"):
                lookup[base] = (
                    var.get("name", ""),
                    var.get("description", ""),
                )
    return lookup


def derive_concept_name(concept_id, description):
    """Derive a human-readable concept name from concept_id and description.

    Uses the first sentence of the description if short enough, otherwise
    title-cases the concept_id.

    Args:
        concept_id: e.g. "bp_systolic"
        description: Full description text.

    Returns:
        Human-readable name string.
    """
    # Map of known concept_id prefixes to readable names
    name_overrides = {
        "annotated_sex": "Annotated Sex",
        "age_at_index": "Age at Index",
        "bmi": "Body Mass Index (BMI)",
        "current_smoker": "Current Smoker Status",
        "ever_smoker": "Ever Smoker Status",
        "height": "Standing Height",
        "weight": "Body Weight",
        "race": "Race",
        "hispanic_or_latino": "Hispanic or Latino Ethnicity",
    }
    if concept_id in name_overrides:
        return name_overrides[concept_id]

    # For most concepts, title-case the concept_id with underscores as spaces
    # e.g. "bp_systolic" -> "Bp Systolic" -> fix common abbreviations
    name = concept_id.replace("_", " ").title()
    # Fix common abbreviations
    abbrevs = {
        "Bp ": "Blood Pressure - ",
        "Hdl": "HDL",
        "Ldl": "LDL",
        "Vte": "VTE",
        "Wbc": "WBC",
        "Rbc": "RBC",
        "Mcv": "MCV",
        "Mch": "MCH",
        "Mchc": "MCHC",
        "Rdw": "RDW",
        "Mpv": "MPV",
        "Pmv": "PMV",
        "Crp": "CRP",
        "Hba1C": "HbA1c",
        "Cac": "CAC",
        "Cabg": "CABG",
        "Vte ": "VTE ",
        "Il6": "IL-6",
        "Il 6": "IL-6",
        "Icam1": "ICAM-1",
        "Cimt": "CIMT",
        "Ncnc Bld": "(Number Concentration in Blood)",
        "Mcnc Bld": "(Mass Concentration in Blood)",
        "Entmass Bld": "(Mass per Entity in Blood)",
        "Entvol Bld": "(Volume per Entity in Blood)",
        "Vfr Bld": "(Volume Fraction in Blood)",
    }
    for pattern, replacement in abbrevs.items():
        name = name.replace(pattern, replacement)
    return name


def extract_concepts():
    """Extract seed concepts from all harmonized variable JSON files.

    Returns:
        List of concept dicts with component variables.
    """
    phs_mapping = load_phs_mapping()
    concepts = []

    json_files = sorted(HARMONIZED_DIR.rglob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {HARMONIZED_DIR}", file=sys.stderr)
        sys.exit(1)

    for json_path in json_files:
        with open(json_path) as f:
            data = json.load(f)

        concept_id = data["phenotype_concept"]
        description = data.get("description", "")
        measurement_units = data.get("measurement_units")
        domain = json_path.parent.name  # parent directory = domain

        # Extract UMLS CUI
        cui = None
        for cv in data.get("controlled_vocabulary", []):
            if cv.get("source") == "UMLS":
                cui = cv["id"]
                break

        # Extract component variables from all harmonization units
        component_variables = []
        for unit in data.get("harmonization_units", []):
            study_name = unit["name"]
            for var_str in unit.get("component_study_variables", []):
                parsed = parse_component_variable(var_str)
                if parsed:
                    # Try phs_mapping first, fall back to harmonization unit name
                    resolved_study = phs_mapping.get(parsed["phs"], study_name)
                    component_variables.append(
                        {
                            "phv": parsed["phv"],
                            "phs": parsed["phs"],
                            "pht": parsed["pht"],
                            "study_name": resolved_study,
                        }
                    )

        concepts.append(
            {
                "concept_id": concept_id,
                "description": description,
                "cui": cui,
                "domain": domain,
                "measurement_units": measurement_units,
                "component_variables": component_variables,
            }
        )

    return concepts


def enrich_with_parsed_tables(concepts, phv_lookup):
    """Add variable_name and variable_description from parsed-tables.json.

    Args:
        concepts: List of concept dicts (mutated in place).
        phv_lookup: Dict mapping phv ID to (name, description).

    Returns:
        Count of matched and unmatched phv IDs.
    """
    matched = 0
    unmatched = 0
    for concept in concepts:
        for comp in concept["component_variables"]:
            phv = _phv_base(comp["phv"])
            if phv in phv_lookup:
                name, desc = phv_lookup[phv]
                comp["variable_name"] = name
                comp["variable_description"] = desc
                matched += 1
            else:
                unmatched += 1
    return matched, unmatched


def _score_example_relevance(concept_id, variable_name, variable_description):
    """Score how relevant a component variable is as an example for its concept.

    Prefers variables whose name/description clearly relate to the concept,
    filtering out generic covariates (age, visit, consent) that happen to
    be co-referenced in harmonization units.

    Args:
        concept_id: e.g. "bp_systolic"
        variable_name: e.g. "SBPA21"
        variable_description: e.g. "SITTING SYSTOLIC BLOOD PRESSURE"

    Returns:
        Integer score (higher = more relevant).
    """
    desc_lower = variable_description.lower()
    name_lower = variable_name.lower()

    # Penalize generic covariates that are not about the concept itself
    generic_terms = ("age", "visit", "exam", "consent", "gender", "sex", "race")
    for term in generic_terms:
        if term in name_lower or desc_lower.startswith(term):
            # Unless the concept is actually about that term
            if term not in concept_id.lower():
                return -1

    # Build keywords from concept_id: "bp_systolic" -> ["bp", "systolic"]
    keywords = concept_id.lower().replace("_", " ").split()

    score = 0
    for kw in keywords:
        if kw in desc_lower:
            score += 2
        if kw in name_lower:
            score += 1

    return score


def build_concept_vocabulary(concepts):
    """Build the LLM matching vocabulary from enriched seed concepts.

    Selects 2-3 example variables per concept, preferring variables whose
    names/descriptions are most relevant to the concept (not generic
    covariates like age or visit).

    Args:
        concepts: List of enriched concept dicts.

    Returns:
        List of vocabulary entry dicts.
    """
    vocabulary = []
    for concept in concepts:
        # Collect all resolved candidates
        candidates = []
        seen_names = set()
        for comp in concept["component_variables"]:
            vname = comp.get("variable_name", "")
            vdesc = comp.get("variable_description", "")
            if vname and vdesc and vname not in seen_names:
                score = _score_example_relevance(
                    concept["concept_id"], vname, vdesc
                )
                candidates.append((score, vname, vdesc))
                seen_names.add(vname)

        # Sort by relevance score descending, pick top 3
        candidates.sort(key=lambda x: x[0], reverse=True)
        examples = [f"{c[1]}: {c[2]}" for c in candidates[:3]]

        vocabulary.append(
            {
                "concept_id": concept["concept_id"],
                "name": derive_concept_name(
                    concept["concept_id"], concept["description"]
                ),
                "description": concept["description"],
                "cui": concept["cui"],
                "domain": concept["domain"],
                "example_variables": examples,
            }
        )

    return vocabulary


def main():
    """Run the full extraction pipeline."""
    print("Step 1: Extracting concepts from harmonized variable JSONs...")
    concepts = extract_concepts()
    total_components = sum(len(c["component_variables"]) for c in concepts)
    all_studies = set()
    for c in concepts:
        for comp in c["component_variables"]:
            all_studies.add(comp["study_name"])

    print(f"  Found {len(concepts)} concepts, {total_components} component variables")
    print(f"  Across {len(all_studies)} studies")

    print("\nStep 2: Loading parsed-tables.json for cross-reference...")
    with open(PARSED_TABLES_FILE) as f:
        parsed_tables = json.load(f)
    print(f"  Loaded {len(parsed_tables)} tables")

    phv_lookup = build_phv_lookup(parsed_tables)
    print(f"  Built lookup with {len(phv_lookup)} unique phv IDs")

    print("\nStep 3: Enriching component variables with names/descriptions...")
    matched, unmatched = enrich_with_parsed_tables(concepts, phv_lookup)
    print(f"  Matched: {matched}, Unmatched: {unmatched}")

    # Build stats
    stats = {
        "total_concepts": len(concepts),
        "total_component_variables": total_components,
        "total_studies": len(all_studies),
        "cross_reference_matched": matched,
        "cross_reference_unmatched": unmatched,
    }

    # Write seed concepts
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seed_path = OUTPUT_DIR / "topmed-seed-concepts.json"
    with open(seed_path, "w") as f:
        json.dump({"concepts": concepts, "stats": stats}, f, indent=2)
    print(f"\nWrote {seed_path}")

    # Build and write concept vocabulary
    print("\nStep 4: Building concept vocabulary for LLM matching...")
    vocabulary = build_concept_vocabulary(concepts)
    vocab_path = OUTPUT_DIR / "concept-vocabulary.json"
    with open(vocab_path, "w") as f:
        json.dump(vocabulary, f, indent=2)
    print(f"Wrote {vocab_path}")

    # Summary
    concepts_with_examples = sum(
        1 for v in vocabulary if len(v["example_variables"]) > 0
    )
    print(f"\n--- Summary ---")
    print(f"Concepts: {len(concepts)}")
    print(f"Component variables: {total_components}")
    print(f"Studies: {len(all_studies)}")
    print(f"Cross-ref matched: {matched}/{total_components}")
    print(f"Concepts with example variables: {concepts_with_examples}/{len(concepts)}")


if __name__ == "__main__":
    main()
