#!/usr/bin/env python3
"""Generate sub-concepts for broad parent concepts using an LLM.

Scans v4 classification output, collects variables under a target concept,
sends deduplicated (variable_name, description) pairs to Sonnet to produce
a shallow navigation tree of 20-50 sub-categories, then updates:

- concept-vocabulary.json (appends sub-concept entries)
- concept-isa.json (appends sub-concept → parent ISA rows)
- llm-concepts-v4/phs*.json (re-tags variables with sub-concept IDs)

Usage:
    python build_subconcepts.py                                  # All targets
    python build_subconcepts.py --concept topmed:food_frequency_questionnaire
    python build_subconcepts.py --dry-run                        # Show prompt only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Clear Claude Code sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

LLM_DIR = SCRIPT_DIR / "output" / "llm-concepts-v4"
VOCAB_PATH = SCRIPT_DIR / "output" / "concept-vocabulary.json"
ISA_PATH = SCRIPT_DIR / "output" / "concept-isa.json"

MODEL = "anthropic:claude-sonnet-4-20250514"

# Concepts eligible for sub-concept expansion.
# Maps concept_id → short prefix used for generated sub-concept IDs.
TARGET_CONCEPTS: dict[str, str] = {
    "topmed:food_frequency_questionnaire": "ncpi:ffq",
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class SubConceptWithMembers(BaseModel):
    """A sub-concept category with its assigned variables."""

    concept_id: str = Field(
        description=(
            "Short snake_case slug for this sub-concept "
            "(e.g. 'chocolate' → stored as '<prefix>_chocolate')"
        )
    )
    name: str = Field(description="Human-readable category name")
    description: str = Field(
        description="What this sub-concept covers (foods, nutrients, etc.)"
    )
    variables: list[str] = Field(
        description="Variable names assigned to this category (exact match from input)"
    )


class NavigationTree(BaseModel):
    """LLM output: a shallow navigation tree of sub-concepts."""

    categories: list[SubConceptWithMembers] = Field(
        description="20-50 sub-concept categories with assigned variables"
    )

    @model_validator(mode="after")
    def validate_tree(self) -> NavigationTree:
        """Check structural constraints."""
        ids = [c.concept_id for c in self.categories]
        if len(ids) != len(set(ids)):
            dupes = [x for x in ids if ids.count(x) > 1]
            msg = f"Duplicate concept_ids: {set(dupes)}"
            raise ValueError(msg)
        if len(self.categories) < 5:
            msg = f"Too few categories: {len(self.categories)} (expected ≥ 5)"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a biomedical data cataloger. Your task is to sort research variables
into a shallow navigation tree for search.

You will receive a list of (variable_name, description) pairs that all belong
to a single broad measurement concept. Create 20-50 sub-categories that a
researcher could use to drill down.

Rules:
- Each category needs a short snake_case concept_id slug (e.g. "chocolate",
  "dairy", "alcohol_beverages"). The slug will be prefixed automatically.
- Each category needs a human-readable name and a description that explains
  what it covers — be specific enough that an LLM reading the description
  can decide if a query matches.
- Assign EVERY input variable to exactly one category.
- Use the variable's description (not just its name) to decide placement.
- Prefer categories that map to how researchers think about the domain
  (food groups, nutrient types, dietary patterns, etc.).
- Aim for 20-50 categories. Merge tiny groups; split huge ones.
- Return variable names EXACTLY as given in the input (case-sensitive).
"""


def build_user_prompt(
    parent_concept: str,
    variables: list[dict],
) -> str:
    """Build the user prompt with variable list.

    Args:
        parent_concept: The parent concept being expanded.
        variables: Deduplicated variable dicts with 'name' and 'description'.

    Returns:
        Formatted user prompt string.
    """
    lines = [
        f"## Parent concept: `{parent_concept}`\n",
        f"Sort these {len(variables)} variables into 20-50 sub-categories.\n",
        "## Variables\n",
    ]
    for v in variables:
        lines.append(f"- **{v['name']}**: {v['description']}")
    lines.append(
        "\n\nProduce the navigation tree. Remember:\n"
        "- 20-50 categories with name, description, and assigned variables\n"
        "- Every variable must be assigned to exactly one category\n"
        "- Return variable names exactly as shown above"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Variable collection
# ---------------------------------------------------------------------------


def collect_variables(
    concept_id: str,
) -> tuple[list[dict], dict[str, list[tuple[str, str, int, int]]]]:
    """Scan v4 output and collect variables for a concept.

    Args:
        concept_id: The concept_id to collect variables for.

    Returns:
        Tuple of:
        - Deduplicated variable list: [{name, description}]
        - Location index: name_lower → [(study_path_stem, table_idx, var_idx, ...)]
    """
    seen: dict[tuple[str, str], dict] = {}  # (name_lower, desc_lower) → {name, description}
    locations: dict[str, list[tuple[str, int, int]]] = {}  # name_lower → [(stem, table_i, var_i)]

    for path in sorted(LLM_DIR.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        for ti, table in enumerate(data.get("tables", [])):
            for vi, var in enumerate(table.get("variables", [])):
                if var.get("concept_id") != concept_id:
                    continue
                name = var.get("name", "")
                desc = var.get("description", "")
                key = (name.lower(), desc.lower())
                if key not in seen:
                    seen[key] = {"name": name, "description": desc}
                locations.setdefault(name.lower(), []).append(
                    (path.stem, ti, vi)
                )

    variables = sorted(seen.values(), key=lambda v: v["name"].lower())
    return variables, locations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def generate_subconcepts(
    concept_id: str,
    prefix: str,
    dry_run: bool = False,
) -> None:
    """Generate sub-concepts for one parent concept.

    Args:
        concept_id: Parent concept to expand (e.g. "topmed:food_frequency_questionnaire").
        prefix: ID prefix for generated sub-concepts (e.g. "topmed:ffq").
        dry_run: If True, print the prompt and exit without calling the LLM.
    """
    print(f"\n{'='*60}")
    print(f"Expanding: {concept_id}")
    print(f"Prefix: {prefix}")
    print(f"{'='*60}\n")

    # Step 1: Collect variables
    variables, locations = collect_variables(concept_id)
    print(f"Found {len(variables)} unique (name, description) pairs")
    total_locs = sum(len(v) for v in locations.values())
    print(f"Total variable occurrences across studies: {total_locs}")

    if not variables:
        print("No variables found — skipping")
        return

    # Step 2: Build prompt
    user_prompt = build_user_prompt(concept_id, variables)

    if dry_run:
        print(f"\n=== SYSTEM PROMPT ({len(SYSTEM_PROMPT)} chars) ===")
        print(SYSTEM_PROMPT)
        print(f"\n=== USER PROMPT ({len(user_prompt)} chars) ===")
        print(user_prompt[:5000])
        if len(user_prompt) > 5000:
            print(f"... ({len(user_prompt) - 5000} more chars)")
        return

    # Step 3: Call LLM
    # Use a custom client with a higher timeout because the large output
    # (5K+ variable names) triggers the SDK's 10-minute streaming guard.
    # Setting a non-default timeout bypasses the check in beta.messages.create.
    client = AsyncAnthropic(
        timeout=httpx.Timeout(1800.0, connect=10.0)
    )
    model = AnthropicModel(
        "claude-sonnet-4-20250514",
        provider=AnthropicProvider(anthropic_client=client),
    )
    agent = Agent(
        model,
        output_type=NavigationTree,
        system_prompt=SYSTEM_PROMPT,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            max_tokens=32768,
            temperature=0.0,
        ),
    )

    print("Calling LLM to generate navigation tree...")
    result = await agent.run(user_prompt)
    tree = result.output

    print(f"Generated {len(tree.categories)} categories")

    # Validate all variables assigned
    all_input_names = {v["name"] for v in variables}
    assigned_names: set[str] = set()
    for cat in tree.categories:
        assigned_names.update(cat.variables)

    missing = all_input_names - assigned_names
    extra = assigned_names - all_input_names
    if missing:
        print(f"WARNING: {len(missing)} variables not assigned to any category")
        for m in sorted(missing)[:10]:
            print(f"  {m}")
    if extra:
        print(f"WARNING: {len(extra)} variable names not in input (typos?)")
        for e in sorted(extra)[:10]:
            print(f"  {e}")

    # Build variable → sub-concept mapping
    var_to_subconcept: dict[str, str] = {}
    for cat in tree.categories:
        full_id = f"{prefix}_{cat.concept_id}"
        for vname in cat.variables:
            var_to_subconcept[vname.lower()] = full_id

    # Step 4: Write outputs

    # 4a. Append to concept-vocabulary.json
    with open(VOCAB_PATH) as f:
        vocab = json.load(f)

    existing_ids = {e["concept_id"] for e in vocab}
    # Determine domain from parent concept vocabulary entry
    parent_bare = concept_id.split(":", 1)[-1] if ":" in concept_id else concept_id
    parent_entry = next((e for e in vocab if e["concept_id"] == parent_bare), None)
    domain = parent_entry["domain"] if parent_entry else "unknown"

    new_vocab_entries = []
    for cat in tree.categories:
        full_id = f"{prefix}_{cat.concept_id}"
        bare_id = full_id.split(":", 1)[-1] if ":" in full_id else full_id
        if bare_id not in existing_ids:
            new_vocab_entries.append({
                "concept_id": bare_id,
                "cui": None,
                "description": cat.description,
                "domain": domain,
                "example_variables": cat.variables[:5],
                "name": cat.name,
            })

    vocab.extend(new_vocab_entries)
    with open(VOCAB_PATH, "w") as f:
        json.dump(vocab, f, indent=2)
    print(f"Appended {len(new_vocab_entries)} entries to {VOCAB_PATH.name}")

    # 4b. Append to concept-isa.json
    with open(ISA_PATH) as f:
        isa = json.load(f)

    existing_pairs = {(e["child"], e["parent"]) for e in isa}
    new_isa = []
    for cat in tree.categories:
        full_id = f"{prefix}_{cat.concept_id}"
        pair = (full_id, concept_id)
        if pair not in existing_pairs:
            new_isa.append({"child": full_id, "parent": concept_id})

    isa.extend(new_isa)
    with open(ISA_PATH, "w") as f:
        json.dump(isa, f, indent=2)
    print(f"Appended {len(new_isa)} ISA rows to {ISA_PATH.name}")

    # 4c. Update per-study JSONs to re-tag variables
    retag_count = 0
    for path in sorted(LLM_DIR.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        modified = False
        for table in data.get("tables", []):
            for var in table.get("variables", []):
                if var.get("concept_id") != concept_id:
                    continue
                name = var.get("name", "")
                new_id = var_to_subconcept.get(name.lower())
                if new_id:
                    var["concept_id"] = new_id
                    modified = True
                    retag_count += 1
        if modified:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    print(f"Re-tagged {retag_count} variable occurrences across study files")

    # Summary
    print(f"\nSummary for {concept_id}:")
    for cat in sorted(tree.categories, key=lambda c: -len(c.variables)):
        print(f"  {prefix}_{cat.concept_id}: {cat.name} ({len(cat.variables)} vars)")


async def main_async(args: argparse.Namespace) -> None:
    """Run sub-concept generation for target concepts.

    Args:
        args: Parsed command-line arguments.
    """
    if args.concept:
        if args.concept not in TARGET_CONCEPTS:
            print(f"Unknown concept: {args.concept}")
            print(f"Known targets: {list(TARGET_CONCEPTS.keys())}")
            sys.exit(1)
        targets = {args.concept: TARGET_CONCEPTS[args.concept]}
    else:
        targets = TARGET_CONCEPTS

    for concept_id, prefix in targets.items():
        await generate_subconcepts(concept_id, prefix, dry_run=args.dry_run)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Generate sub-concepts for broad concepts")
    parser.add_argument(
        "--concept", type=str, help="Specific concept_id to expand"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompt without calling LLM"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
