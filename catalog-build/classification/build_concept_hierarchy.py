"""Build a 2-level category hierarchy for variable concepts using LLM.

Reads all concept names from the per-study LLM classification output,
assigns each to a top-level category and mid-level subcategory, and
saves the hierarchy to concept-hierarchy.json.

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python build_concept_hierarchy.py                    # Multi-study concepts only (2+ studies)
    python build_concept_hierarchy.py --all              # All concepts including singletons
    python build_concept_hierarchy.py --min-studies 5    # Only concepts in 5+ studies
    python build_concept_hierarchy.py --sample 500       # Random sample for testing
    python build_concept_hierarchy.py --debug            # Print progress details
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# Clear Claude Code sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.settings import ModelSettings

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

CONCEPT_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts"
HIERARCHY_PATH = SCRIPT_DIR / "output" / "concept-hierarchy.json"

MODEL = "anthropic:claude-haiku-4-5-20251001"
MAX_RETRIES = 5
TOP_BATCH_SIZE = 25
MID_BATCH_SIZE = 30
DEBUG = False

# ---------------------------------------------------------------------------
# Top-level categories
# ---------------------------------------------------------------------------

TOP_LEVEL_CATEGORIES = [
    "Anthropometry",
    "Behavioral & Lifestyle",
    "Biomarkers & Proteins",
    "Cardiovascular",
    "Demographics",
    "Dietary & Nutrition",
    "Endocrine & Metabolic",
    "Genetic & Genomic",
    "Hematology",
    "Imaging & Radiology",
    "Immunology & Inflammation",
    "Infectious Disease",
    "Laboratory Tests",
    "Medications & Treatment",
    "Mental Health & Neurology",
    "Metabolomics",
    "Musculoskeletal",
    "Oncology",
    "Ophthalmology",
    "Pulmonary & Respiratory",
    "Renal & Urinary",
    "Reproductive & Perinatal",
    "Social & Environmental",
    "Study Administration",
    "Surgical & Procedural",
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TopLevelAssignment(BaseModel):
    concept: str
    top_level: str


class TopLevelBatchResult(BaseModel):
    assignments: list[TopLevelAssignment]


class MidLevelAssignment(BaseModel):
    concept: str
    mid_level: str
    is_new: bool


class MidLevelBatchResult(BaseModel):
    assignments: list[MidLevelAssignment]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def _make_top_agent(model: str) -> Agent[None, TopLevelBatchResult]:
    return Agent(
        model,
        output_type=TopLevelBatchResult,
        system_prompt=(
            "You assign medical/clinical concepts to top-level categories.\n\n"
            "Categories:\n"
            + "\n".join(f"- {c}" for c in TOP_LEVEL_CATEGORIES)
            + "\n\nRules:\n"
            "- Assign exactly ONE top-level category per concept.\n"
            "- Use the category name exactly as listed.\n"
            "- Return one assignment per input concept, in order.\n"
            "- For concepts about specific body systems, prefer the system-specific "
            "category (e.g., 'Systolic Blood Pressure' → 'Cardiovascular').\n"
            "- Study identifiers, consent, visit info → 'Study Administration'.\n"
            "- Age, sex, race, education → 'Demographics'.\n"
            "- Smoking, alcohol, exercise → 'Behavioral & Lifestyle'.\n"
            "- Individual food items, diet → 'Dietary & Nutrition'.\n"
            "- miRNA, proteins, cytokines → 'Biomarkers & Proteins'.\n"
            "- Metabolites, lipids → 'Metabolomics' if specific compound, "
            "'Laboratory Tests' if a standard clinical test.\n"
        ),
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )


def _make_mid_agent(model: str) -> Agent[None, MidLevelBatchResult]:
    return Agent(
        model,
        output_type=MidLevelBatchResult,
        system_prompt=(
            "You organize medical concepts into mid-level subcategories within a "
            "given top-level category.\n\n"
            "You receive:\n"
            "- A top-level category name\n"
            "- A list of existing mid-level subcategories (may be empty)\n"
            "- A batch of concepts to classify\n\n"
            "For each concept, either:\n"
            "1. Place it under an existing mid-level (set is_new=false), OR\n"
            "2. Create a new mid-level name (set is_new=true)\n\n"
            "Rules for mid-level names:\n"
            "- Use standard medical terminology (UMLS preferred terms when possible)\n"
            "- Mid-levels should group 5-50 related concepts — not too broad, "
            "not too narrow\n"
            "- Examples: 'Blood Pressure', 'Cholesterol', 'Electrocardiography', "
            "'Smoking', 'Alcohol Use', 'Body Composition'\n"
            "- Do NOT create a mid-level for a single concept unless it's clearly "
            "distinct from all existing mid-levels\n"
            "- Prefer reusing existing mid-levels over creating new ones\n"
            "- Return one assignment per input concept, in order.\n"
        ),
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_concepts(output_dir: Path) -> dict[str, int]:
    """Load all concepts with study counts from per-study JSON files.

    Returns dict of concept_name -> study_count, sorted by count descending.
    """
    concept_studies: dict[str, set[str]] = defaultdict(set)
    for path in sorted(output_dir.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        study_id = data.get("studyId", path.stem)
        for table in data.get("tables", []):
            for var in table.get("variables", []):
                concept = var.get("concept")
                if concept:
                    concept_studies[concept].add(study_id)

    # Sort by study count descending, then alphabetically
    return dict(
        sorted(
            ((c, len(s)) for c, s in concept_studies.items()),
            key=lambda x: (-x[1], x[0]),
        )
    )


# ---------------------------------------------------------------------------
# LLM batch processing with retry
# ---------------------------------------------------------------------------


async def _run_with_retry(agent, prompt: str, max_retries: int = MAX_RETRIES):
    """Run agent with exponential backoff on rate limits."""
    for attempt in range(1, max_retries + 1):
        try:
            return await agent.run(prompt)
        except ModelHTTPError as e:
            if e.status_code == 429 and attempt < max_retries:
                wait = 2**attempt
                print(f"    Rate limited, retrying in {wait}s...", file=sys.stderr)
                await asyncio.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Pass 1: Top-level assignment
# ---------------------------------------------------------------------------


async def assign_top_levels(
    concepts: list[str], model: str
) -> dict[str, str]:
    """Assign a top-level category to each concept.

    Returns dict of concept_name -> top_level_category.
    """
    agent = _make_top_agent(model)
    concept_top: dict[str, str] = {}
    total_batches = (len(concepts) + TOP_BATCH_SIZE - 1) // TOP_BATCH_SIZE

    for i in range(0, len(concepts), TOP_BATCH_SIZE):
        batch = concepts[i : i + TOP_BATCH_SIZE]
        prompt = "Assign top-level categories:\n\n"
        prompt += "\n".join(f"- {c}" for c in batch)
        batch_num = i // TOP_BATCH_SIZE + 1

        if DEBUG:
            print(
                f"  Top-level batch {batch_num}/{total_batches} "
                f"({len(batch)} concepts)...",
                file=sys.stderr,
            )
        else:
            print(
                f"\r  Top-level: {batch_num}/{total_batches}",
                end="",
                file=sys.stderr,
                flush=True,
            )

        try:
            result = await _run_with_retry(agent, prompt)
            for a in result.output.assignments:
                concept_top[a.concept] = a.top_level
        except Exception as e:
            print(f"\n    ERROR batch {batch_num}: {e}", file=sys.stderr)
            for c in batch:
                concept_top[c] = "Other"

    if not DEBUG:
        print(file=sys.stderr)  # newline after progress
    return concept_top


# ---------------------------------------------------------------------------
# Pass 2: Mid-level assignment
# ---------------------------------------------------------------------------


async def assign_mid_levels(
    top_groups: dict[str, list[str]], model: str
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Assign mid-level subcategories within each top-level.

    Processes top-levels from largest to smallest. Within each top-level,
    mid-level categories accumulate as concepts are processed.

    Returns:
        concept_mid: dict of concept_name -> mid_level
        mid_levels_by_top: dict of top_level -> set of mid_level names
    """
    agent = _make_mid_agent(model)
    concept_mid: dict[str, str] = {}
    mid_levels_by_top: dict[str, set[str]] = defaultdict(set)

    # Process largest groups first so mid-levels accumulate from common concepts
    sorted_groups = sorted(top_groups.items(), key=lambda x: -len(x[1]))

    for tl, concepts in sorted_groups:
        if tl in ("UNKNOWN", "Other"):
            for c in concepts:
                concept_mid[c] = "Other"
            continue

        existing_mids = mid_levels_by_top[tl]
        total_batches = (len(concepts) + MID_BATCH_SIZE - 1) // MID_BATCH_SIZE
        print(
            f"  Mid-level: {tl} ({len(concepts)} concepts, "
            f"{total_batches} batches)...",
            file=sys.stderr,
        )

        for i in range(0, len(concepts), MID_BATCH_SIZE):
            batch = concepts[i : i + MID_BATCH_SIZE]
            mid_list = sorted(existing_mids) if existing_mids else ["(none yet)"]
            prompt = (
                f"Top-level category: {tl}\n\n"
                f"Existing mid-level subcategories:\n"
                + "\n".join(f"- {m}" for m in mid_list)
                + f"\n\nAssign mid-level for these concepts:\n"
                + "\n".join(f"- {c}" for c in batch)
            )
            try:
                result = await _run_with_retry(agent, prompt)
                for a in result.output.assignments:
                    concept_mid[a.concept] = a.mid_level
                    existing_mids.add(a.mid_level)
            except Exception as e:
                batch_num = i // MID_BATCH_SIZE + 1
                print(f"    ERROR batch {batch_num}: {e}", file=sys.stderr)
                for c in batch:
                    concept_mid[c] = "Other"

        print(
            f"    → {len(existing_mids)} mid-level categories",
            file=sys.stderr,
        )

    return concept_mid, mid_levels_by_top


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------


def save_hierarchy(
    concept_top: dict[str, str],
    concept_mid: dict[str, str],
    concept_counts: dict[str, int],
    mid_levels_by_top: dict[str, set[str]],
    output_path: Path,
) -> None:
    """Save hierarchy in two formats: per-concept lookup and nested tree."""
    # Per-concept lookup
    concepts: dict[str, dict] = {}
    for c in concept_top:
        concepts[c] = {
            "top_level": concept_top.get(c, "Other"),
            "mid_level": concept_mid.get(c, "Other"),
            "study_count": concept_counts.get(c, 0),
        }

    # Nested tree: top_level -> mid_level -> [concepts]
    hierarchy: dict[str, dict[str, list[dict]]] = {}
    for c, info in sorted(concepts.items(), key=lambda x: x[0]):
        tl = info["top_level"]
        ml = info["mid_level"]
        if tl not in hierarchy:
            hierarchy[tl] = {}
        if ml not in hierarchy[tl]:
            hierarchy[tl][ml] = []
        hierarchy[tl][ml].append({
            "concept": c,
            "study_count": info["study_count"],
        })

    # Sort concepts within each mid-level by study count descending
    for tl in hierarchy:
        for ml in hierarchy[tl]:
            hierarchy[tl][ml].sort(key=lambda x: -x["study_count"])

    result = {
        "concepts": concepts,
        "hierarchy": hierarchy,
        "stats": {
            "total_concepts": len(concepts),
            "top_level_categories": len(hierarchy),
            "mid_level_categories": sum(
                len(mids) for mids in hierarchy.values()
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(f"\nSaved to {output_path}", file=sys.stderr)
    print(
        f"  {result['stats']['total_concepts']} concepts → "
        f"{result['stats']['top_level_categories']} top-level → "
        f"{result['stats']['mid_level_categories']} mid-level",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def build_hierarchy(
    min_studies: int = 2,
    sample_size: int | None = None,
    model: str = MODEL,
) -> None:
    """Build the concept hierarchy and save to JSON."""
    print("Loading concepts...", file=sys.stderr)
    concept_counts = load_concepts(CONCEPT_OUTPUT_DIR)
    print(f"  {len(concept_counts)} unique concepts", file=sys.stderr)

    # Filter by study count
    filtered = {c: n for c, n in concept_counts.items() if n >= min_studies}
    print(
        f"  {len(filtered)} concepts with {min_studies}+ studies",
        file=sys.stderr,
    )

    concepts = list(filtered.keys())

    # Optional sampling
    if sample_size and sample_size < len(concepts):
        random.seed(42)
        concepts = random.sample(concepts, sample_size)
        print(f"  Sampled {len(concepts)} concepts", file=sys.stderr)

    start = time.time()

    # Pass 1: Top-level
    print(f"\n--- Pass 1: Top-level assignment ({len(concepts)} concepts) ---", file=sys.stderr)
    concept_top = await assign_top_levels(concepts, model)

    # Group by top-level, sorted by study count within each group
    top_groups: dict[str, list[str]] = defaultdict(list)
    for c in concepts:
        tl = concept_top.get(c, "Other")
        top_groups[tl].append(c)

    print(f"\nTop-level distribution:", file=sys.stderr)
    for tl, cs in sorted(top_groups.items(), key=lambda x: -len(x[1])):
        print(f"  {len(cs):5d}  {tl}", file=sys.stderr)

    # Pass 2: Mid-level
    print(f"\n--- Pass 2: Mid-level assignment ---", file=sys.stderr)
    concept_mid, mid_levels_by_top = await assign_mid_levels(top_groups, model)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s ({elapsed / len(concepts):.2f}s per concept)", file=sys.stderr)

    # Save
    save_hierarchy(
        concept_top, concept_mid, concept_counts, mid_levels_by_top,
        HIERARCHY_PATH,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build concept hierarchy")
    parser.add_argument(
        "--all", action="store_true",
        help="Include all concepts (including singletons)",
    )
    parser.add_argument(
        "--min-studies", type=int, default=2,
        help="Minimum study count to include (default: 2)",
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Random sample size for testing",
    )
    parser.add_argument(
        "--model", default=MODEL,
        help=f"Model to use (default: {MODEL})",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Print verbose progress",
    )
    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    min_studies = 1 if args.all else args.min_studies

    asyncio.run(build_hierarchy(
        min_studies=min_studies,
        sample_size=args.sample,
        model=args.model,
    ))


if __name__ == "__main__":
    main()
