"""Extract per-study sex and race/ethnicity distributions.

Reads demographics from two sources:
  1. dbGaP Subject_Phenotypes var_report XML — self-reported sex and
     race/ethnicity from the standardized phenotype table studies submit.
  2. dbGaP advanced search CSV — genetically-inferred ancestry computed
     by dbGaP from genotype data ("Ancestry (computed)" column).

Usage:
    python extract_demographics.py              # Process all studies
    python extract_demographics.py --study phs000209  # Single study
"""

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to this script's location)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DBGAP_VARIABLES_DIR = SCRIPT_DIR.parent / "source" / "dbgap-variables"
DBGAP_CSV = SCRIPT_DIR.parent / "source" / "2026-01-27-dbgap-advanced-search.csv"
OUTPUT_FILE = SCRIPT_DIR / "output" / "demographic-profiles.json"

# ---------------------------------------------------------------------------
# Variable name patterns (case-insensitive)
# ---------------------------------------------------------------------------

SEX_NAME_RE = re.compile(r"sex|gender", re.IGNORECASE)
RACE_NAME_RE = re.compile(r"race|ethni", re.IGNORECASE)
ANCESTRY_RE = re.compile(r"([^,]+?)\s*\((\d+)\)")


def is_consent_variant(variable_id: str) -> bool:
    """Check if a variable ID is a consent-specific variant (e.g. .c1, .c2)."""
    parts = variable_id.split(".")
    return len(parts) >= 4 and parts[-1].startswith("c")


def classify_variable_name(name: str) -> tuple[bool, bool]:
    """Classify a variable name as sex and/or race/ethnicity.

    Returns (is_sex, is_race).
    """
    return bool(SEX_NAME_RE.search(name)), bool(RACE_NAME_RE.search(name))


def parse_ancestry_string(raw: str) -> list[dict]:
    """Parse a dbGaP computed ancestry string into category dicts.

    Input format: 'European (60), African American (30), East Asian (10)'
    Returns list of {'label': str, 'count': int} sorted by count descending.
    """
    categories = []
    for match in ANCESTRY_RE.finditer(raw):
        label = match.group(1).strip()
        count = int(match.group(2))
        categories.append({"count": count, "label": label})
    categories.sort(key=lambda c: c["count"], reverse=True)
    return categories

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VariableDistribution:
    categories: list[dict]
    dataset_id: str
    n: int
    name: str
    nulls: int
    table_name: str
    variable_id: str


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def load_computed_ancestry() -> dict[str, list[dict]]:
    """Load genetically-inferred ancestry from the dbGaP advanced search CSV.

    Parses the 'Ancestry (computed)' column, which has the format:
        'Label (count), Label (count), ...'

    Returns a dict mapping study_id (e.g., 'phs000209') to a list of
    {'label': str, 'count': int} dicts sorted by count descending.
    """
    ancestry: dict[str, list[dict]] = {}
    if not DBGAP_CSV.exists():
        return ancestry

    with open(DBGAP_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("Ancestry (computed)", "").strip()
            if not raw:
                continue
            accession = row.get("accession", "")
            study_id = accession.split(".")[0]
            if not study_id:
                continue

            categories = parse_ancestry_string(raw)
            if categories:
                ancestry[study_id] = categories

    return ancestry


def find_subject_phenotypes(study_id: str) -> Path | None:
    """Find the Subject_Phenotypes var_report XML for a study.

    Only matches files belonging to the study's own ID (not sub-studies).
    """
    study_dir = DBGAP_VARIABLES_DIR / study_id
    if not study_dir.is_dir():
        return None
    for xml_path in study_dir.glob(
        f"{study_id}.*_Subject_Phenotypes.var_report.xml"
    ):
        return xml_path
    return None


def parse_subject_phenotypes(
    xml_path: Path,
) -> tuple[str, list[VariableDistribution], list[VariableDistribution]]:
    """Parse a Subject_Phenotypes XML and extract sex and race distributions.

    Returns (study_name, sex_distributions, race_distributions).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract metadata from the <data_table> root element
    study_name = root.get("study_name", "")
    dataset_id = root.get("dataset_id", "")
    table_name = root.get("name", "")

    sex_distributions: list[VariableDistribution] = []
    race_distributions: list[VariableDistribution] = []

    for var_elem in root.findall(".//variable"):
        var_id = var_elem.get("id", "")

        if is_consent_variant(var_id):
            continue

        var_name = var_elem.get("var_name", "")

        is_sex, is_race = classify_variable_name(var_name)
        if not is_sex and not is_race:
            continue

        # Extract distribution
        dist = extract_distribution(var_elem, var_name, var_id, dataset_id, table_name)
        if dist is None:
            continue

        if is_sex:
            sex_distributions.append(dist)
        if is_race:
            race_distributions.append(dist)

    return study_name, sex_distributions, race_distributions


def extract_distribution(
    var_elem: ET.Element,
    var_name: str,
    var_id: str,
    dataset_id: str,
    table_name: str,
) -> VariableDistribution | None:
    """Extract the enum distribution from a <variable> element.

    Returns None if the variable has no stat element or no enum elements.
    """
    stats = var_elem.find(".//total/stats")
    if stats is None:
        return None

    stat_elem = stats.find("stat")
    if stat_elem is None:
        return None

    try:
        n = int(stat_elem.get("n", "0"))
        nulls = int(stat_elem.get("nulls", "0"))
    except (ValueError, TypeError):
        return None

    # Extract <enum> elements (direct children of <stats>)
    enums = stats.findall("enum")
    if not enums:
        return None

    categories = []
    for enum_elem in enums:
        try:
            count = int(enum_elem.get("count", "0"))
        except (ValueError, TypeError):
            count = 0
        categories.append(
            {
                "code": enum_elem.get("code"),
                "count": count,
                "label": (enum_elem.text or "").strip(),
            }
        )

    # Sort categories by count descending
    categories.sort(key=lambda c: c["count"], reverse=True)

    return VariableDistribution(
        categories=categories,
        dataset_id=dataset_id,
        n=n,
        name=var_name,
        nulls=nulls,
        table_name=table_name,
        variable_id=var_id,
    )


def select_best_variable(
    distributions: list[VariableDistribution],
) -> VariableDistribution | None:
    """Select the best variable: highest n, then fewest nulls."""
    if not distributions:
        return None
    distributions.sort(key=lambda d: (-d.n, d.nulls))
    return distributions[0]


def distribution_to_dict(dist: VariableDistribution) -> dict:
    """Convert a VariableDistribution to output dict."""
    return {
        "categories": dist.categories,
        "datasetId": dist.dataset_id,
        "n": dist.n,
        "nulls": dist.nulls,
        "tableName": dist.table_name,
        "variableId": dist.variable_id,
        "variableName": dist.name,
    }


def process_study(
    study_id: str,
    computed_ancestry: dict[str, list[dict]] | None = None,
) -> dict | None:
    """Process a single study and return its demographic profile."""
    xml_path = find_subject_phenotypes(study_id)
    ancestry = (computed_ancestry or {}).get(study_id)

    if xml_path is None and ancestry is None:
        return None

    study_name = ""
    best_sex = None
    best_race = None

    if xml_path is not None:
        try:
            study_name, sex_dists, race_dists = parse_subject_phenotypes(xml_path)
        except ET.ParseError:
            pass
        else:
            best_sex = select_best_variable(sex_dists)
            best_race = select_best_variable(race_dists)

    if best_sex is None and best_race is None and ancestry is None:
        return None

    result: dict = {"studyName": study_name}
    if best_sex is not None:
        result["sex"] = distribution_to_dict(best_sex)
    if best_race is not None:
        result["raceEthnicity"] = distribution_to_dict(best_race)
    if ancestry is not None:
        result["computedAncestry"] = {
            "categories": ancestry,
            "n": sum(c["count"] for c in ancestry),
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract per-study sex and race/ethnicity distributions "
        "from dbGaP Subject_Phenotypes tables."
    )
    parser.add_argument(
        "--study",
        help="Process a single study (e.g., phs000209) and print to stdout.",
    )
    args = parser.parse_args()

    print("Loading computed ancestry from dbGaP CSV...")
    computed_ancestry = load_computed_ancestry()
    print(f"  {len(computed_ancestry)} studies with computed ancestry")

    if args.study:
        result = process_study(args.study, computed_ancestry)
        if result is None:
            print(f"No demographic data found for {args.study}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({args.study: result}, indent=2))
        return

    # Full pipeline: process all study directories
    study_ids = sorted(
        {d.name for d in DBGAP_VARIABLES_DIR.iterdir()
         if d.is_dir() and d.name.startswith("phs")}
        | computed_ancestry.keys()
    )

    print(f"Processing {len(study_ids)} studies...")

    studies: dict = {}
    studies_with_sex = 0
    studies_with_race = 0
    studies_with_ancestry = 0
    skipped_no_sp = 0

    for i, study_id in enumerate(study_ids, 1):
        if i % 500 == 0:
            print(f"  {i}/{len(study_ids)}...")

        result = process_study(study_id, computed_ancestry)
        if result is None:
            if find_subject_phenotypes(study_id) is None:
                skipped_no_sp += 1
            continue

        studies[study_id] = result

        if "sex" in result:
            studies_with_sex += 1
        if "raceEthnicity" in result:
            studies_with_race += 1
        if "computedAncestry" in result:
            studies_with_ancestry += 1

    output = {
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "skippedNoSubjectPhenotypes": skipped_no_sp,
            "studiesWithComputedAncestry": studies_with_ancestry,
            "studiesWithRaceEthnicity": studies_with_race,
            "studiesWithSex": studies_with_sex,
            "totalStudies": len(study_ids),
            "totalWithDemographics": len(studies),
        },
        "studies": studies,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {OUTPUT_FILE}")
    print(f"  Total studies: {len(study_ids)}")
    print(f"  With demographics: {len(studies)}")
    print(f"  With sex: {studies_with_sex}")
    print(f"  With race/ethnicity: {studies_with_race}")
    print(f"  With computed ancestry: {studies_with_ancestry}")
    print(f"  Skipped (no Subject_Phenotypes): {skipped_no_sp}")


if __name__ == "__main__":
    main()
