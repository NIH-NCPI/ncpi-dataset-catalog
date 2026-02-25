#!/usr/bin/env python3
"""Generate ISA (is-a) relationships between concept vocabularies using an LLM.

Reads TOPMed, PhenX, and NCPI category vocabularies, asks the LLM to produce
child→parent ISA relationships that form a shallow DAG.

Three layers (flat, max depth 2):
- topmed:* — fine-grained measurement concepts (77)
- phenx:*  — mid-level PhenX protocol concepts (181)
- ncpi:*   — curated top-level categories (20, defined in ncpi-categories.json)

The LLM maps topmed/phenx concepts into the fixed ncpi categories.
It may route topmed→phenx→ncpi when a PhenX protocol is a good intermediary.

Usage:
    python build_concept_isa.py              # Generate ISA table
    python build_concept_isa.py --dry-run    # Show prompt, don't call LLM
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

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModelSettings

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

TOPMED_VOCAB_PATH = SCRIPT_DIR / "output" / "concept-vocabulary.json"
PHENX_VOCAB_PATH = SCRIPT_DIR / "output" / "phenx-concept-vocabulary.json"
NCPI_CATEGORIES_PATH = SCRIPT_DIR / "output" / "ncpi-categories.json"
OUTPUT_PATH = SCRIPT_DIR / "output" / "concept-isa.json"

MODEL = "anthropic:claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class IsaRelationship(BaseModel):
    """A single child→parent ISA relationship."""

    child: str = Field(description="Child concept_id (more specific)")
    parent: str = Field(description="Parent concept_id (more general)")


class IsaResult(BaseModel):
    """Complete ISA table output."""

    relationships: list[IsaRelationship] = Field(
        description="All child→parent ISA relationships"
    )

    @model_validator(mode="after")
    def validate_structure(self) -> IsaResult:
        """Validate ISA constraints: no self-loops, single parent, correct layers."""
        child_to_parents: dict[str, set[str]] = {}
        for r in self.relationships:
            if r.child == r.parent:
                msg = f"Self-loop: {r.child}"
                raise ValueError(msg)
            if r.child.startswith(("topmed:", "phenx:")):
                child_to_parents.setdefault(r.child, set()).add(r.parent)
            if r.child.startswith("phenx:") and not r.parent.startswith("ncpi:"):
                msg = (
                    f"Invalid parent for PhenX concept {r.child}: "
                    f"{r.parent} (expected ncpi:*)"
                )
                raise ValueError(msg)
        for child, parents in child_to_parents.items():
            if len(parents) > 1:
                msg = (
                    f"Multiple parents for {child}: {sorted(parents)}"
                )
                raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a biomedical ontology expert. Your task is to map research \
measurement concepts into a fixed set of categories using ISA (is-a) \
relationships.

You will receive three vocabularies:
1. **NCPI categories** (ncpi:*) — 20 fixed top-level categories. These are \
the ROOTS. You MUST NOT invent new categories or modify these.
2. **TOPMed concepts** (topmed:*) — fine-grained measurement concepts from \
TOPMed harmonized variables.
3. **PhenX concepts** (phenx:*) — mid-level standardized protocol concepts \
from the PhenX Toolkit.

Your job: produce child→parent ISA relationships that map every topmed:* \
and phenx:* concept into the ncpi:* category tree.

Allowed relationship patterns:
- topmed:X → phenx:Y (when a PhenX protocol semantically contains the \
TOPMed concept)
- topmed:X → ncpi:Z (when no good PhenX intermediary exists)
- phenx:Y → ncpi:Z (every PhenX concept must map to an ncpi category)

Rules:
- Every topmed:* concept MUST have exactly one parent (phenx:* or ncpi:*)
- Every phenx:* concept MUST have exactly one parent (ncpi:* only)
- ncpi:* concepts are roots — do NOT assign them parents
- Do NOT invent new ncpi:* categories — use only the ones provided
- The graph must be a DAG — no cycles
- A parent must be semantically MORE GENERAL than its child
- Choose the MOST SPECIFIC valid parent for each concept
- Do NOT create ISA relationships between concepts at the same namespace \
(e.g., topmed:X should not be a child of another topmed:Y)

Key semantic distinctions — the categories encode these, respect them:
- OBSERVATIONS (measurements, test results, biomarker levels) go under \
their physiological category (ncpi:vital_signs, ncpi:biomarkers, etc.)
- MEDICATIONS (drug use status, treatment adherence) go under \
ncpi:medications — never under the condition they treat
- SUBSTANCE USE (tobacco, alcohol, drugs) goes under ncpi:substance_use
- ENVIRONMENTAL EXPOSURES go under ncpi:environment
- DISEASE EVENTS (diagnosis, clinical events) go under ncpi:disease_events
"""


def build_user_prompt(
    topmed_vocab: list[dict],
    phenx_vocab: list[dict],
    ncpi_categories: list[dict],
) -> str:
    """Build the user prompt with all three vocabularies.

    Args:
        topmed_vocab: TOPMed concept vocabulary entries.
        phenx_vocab: PhenX concept vocabulary entries.
        ncpi_categories: NCPI category definitions.

    Returns:
        Formatted user prompt string.
    """
    lines = ["## NCPI Categories (ncpi:*) — FIXED ROOTS\n"]
    for c in ncpi_categories:
        lines.append(
            f"- **{c['concept_id']}**: {c['name']} — {c['description']}"
        )

    lines.append("\n## TOPMed Concepts (topmed:*)\n")
    for c in topmed_vocab:
        cui = c.get("cui", "")
        cui_str = f" [CUI: {cui}]" if cui else ""
        lines.append(
            f"- **{c['concept_id']}**: {c['name']}{cui_str} — "
            f"{c['description']} (domain: {c.get('domain', 'unknown')})"
        )

    lines.append("\n## PhenX Concepts (phenx:*)\n")
    for c in phenx_vocab:
        lines.append(
            f"- **{c['concept_id']}**: {c['name']} "
            f"({c.get('dbgap_variable_count', 0)} mapped variables, "
            f"{c.get('dbgap_study_count', 0)} studies)"
        )

    lines.append(
        "\n\nProduce the ISA relationships. Remember:\n"
        "- Every topmed:* and phenx:* concept must have exactly one parent\n"
        "- Only use ncpi:* categories from the list above — do not invent new ones\n"
        "- phenx:* concepts can only have ncpi:* parents\n"
        "- topmed:* concepts can have phenx:* or ncpi:* parents"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def generate_isa(dry_run: bool = False) -> None:
    """Generate ISA relationships using the LLM.

    Args:
        dry_run: If True, print the prompt and exit without calling the LLM.
    """
    # Load vocabularies
    with open(TOPMED_VOCAB_PATH) as f:
        topmed_vocab = json.load(f)
    with open(PHENX_VOCAB_PATH) as f:
        phenx_vocab = json.load(f)
    with open(NCPI_CATEGORIES_PATH) as f:
        ncpi_categories = json.load(f)

    # Deduplicate TOPMed concepts (there's a duplicate cimt entry)
    seen_ids: set[str] = set()
    deduped_topmed = []
    for c in topmed_vocab:
        cid = c["concept_id"]
        if cid not in seen_ids:
            seen_ids.add(cid)
            # Add topmed: prefix if not already present
            if not cid.startswith("topmed:"):
                c = {**c, "concept_id": f"topmed:{cid}"}
            deduped_topmed.append(c)

    ncpi_ids = {c["concept_id"] for c in ncpi_categories}

    print(f"NCPI categories: {len(ncpi_categories)}")
    print(f"TOPMed concepts: {len(deduped_topmed)}")
    print(f"PhenX concepts: {len(phenx_vocab)}")

    user_prompt = build_user_prompt(deduped_topmed, phenx_vocab, ncpi_categories)

    if dry_run:
        print(f"\n=== SYSTEM PROMPT ({len(SYSTEM_PROMPT)} chars) ===")
        print(SYSTEM_PROMPT)
        print(f"\n=== USER PROMPT ({len(user_prompt)} chars) ===")
        print(user_prompt)
        return

    agent = Agent(
        MODEL,
        output_type=IsaResult,
        system_prompt=SYSTEM_PROMPT,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            max_tokens=16384,
            temperature=0.0,
        ),
    )

    print("Calling LLM to generate ISA relationships...")
    result = await agent.run(user_prompt)
    isa = result.output

    print(f"Generated {len(isa.relationships)} ISA relationships")

    # Validate completeness
    all_topmed = {c["concept_id"] for c in deduped_topmed}
    all_phenx = {c["concept_id"] for c in phenx_vocab}
    children = {r.child for r in isa.relationships}

    missing_topmed = all_topmed - children
    missing_phenx = all_phenx - children

    if missing_topmed:
        print(f"WARNING: {len(missing_topmed)} TOPMed concepts without parents:")
        for m in sorted(missing_topmed):
            print(f"  {m}")
    if missing_phenx:
        print(f"WARNING: {len(missing_phenx)} PhenX concepts without parents:")
        for m in sorted(missing_phenx)[:20]:
            print(f"  {m}")
        if len(missing_phenx) > 20:
            print(f"  ... and {len(missing_phenx) - 20} more")

    # Validate no invented categories
    parents = {r.parent for r in isa.relationships}
    invented = parents - ncpi_ids - all_phenx
    if invented:
        print(f"WARNING: {len(invented)} invented parent IDs (not in ncpi or phenx):")
        for i in sorted(invented):
            print(f"  {i}")

    # Validate phenx parents are only ncpi
    for r in isa.relationships:
        if r.child.startswith("phenx:") and not r.parent.startswith("ncpi:"):
            print(f"WARNING: phenx concept has non-ncpi parent: {r.child} → {r.parent}")

    # Write output
    output = [
        {"child": r.child, "parent": r.parent}
        for r in isa.relationships
    ]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {len(output)} relationships to {OUTPUT_PATH}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Generate concept ISA table")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompt without calling LLM"
    )
    args = parser.parse_args()
    asyncio.run(generate_isa(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
