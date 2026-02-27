#!/usr/bin/env python3
"""Generate variable archetypes for large concepts using an LLM.

Scans v4 classification output, finds concepts with >200 variables,
groups semantically identical variables into "archetypes" (canonical
measurement patterns), then updates:

- concept-vocabulary.json (appends archetype entries)
- concept-isa.json (appends archetype -> parent ISA rows)
- llm-concepts-v4/phs*.json (re-tags variables with archetype IDs)

Archetypes use the ncpi: namespace prefix. For example:
  topmed:ecg -> ncpi:ecg_atrial_fibrillation, ncpi:ecg_qt_interval, ...

Usage:
    python build_archetypes.py                          # All eligible concepts
    python build_archetypes.py --concept topmed:ecg     # Single concept
    python build_archetypes.py --dry-run                # Show stats, no LLM calls
    python build_archetypes.py --min-vars 500           # Custom threshold
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
CACHE_DIR = SCRIPT_DIR / "output" / "archetypes"

DEFAULT_MIN_VARS = 200

# Max unique pairs for the definition call (archetypes + assignments).
# Sonnet 4 has 200K context with 64K max output. At ~22 tokens/pair,
# 3,000 pairs ≈ 66K input + 64K output = 130K total — safe margin.
BATCH_SIZE = 3000

# Max variables per assignment-only call. Output is ~12 tokens per variable
# (compact dict format), so 2,000 * 12 ≈ 24K output tokens — fits in 32K.
ASSIGN_BATCH_SIZE = 2000

MODEL = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class Archetype(BaseModel):
    """A single measurement archetype with its assigned variables."""

    concept_id: str = Field(
        description=(
            "Short snake_case slug for this archetype "
            "(e.g. 'atrial_fibrillation'). Will be prefixed automatically."
        )
    )
    name: str = Field(description="Human-readable archetype name")
    description: str = Field(
        description="What this archetype measures — specific enough for search matching"
    )
    variables: list[str] = Field(
        description="Variable names assigned to this archetype (exact match from input)"
    )


class ArchetypeTree(BaseModel):
    """LLM output: a tree of measurement archetypes."""

    categories: list[Archetype] = Field(
        description="5-50 archetype categories with assigned variables"
    )

    @model_validator(mode="after")
    def validate_tree(self) -> ArchetypeTree:
        """Check structural constraints."""
        ids = [c.concept_id for c in self.categories]
        if len(ids) != len(set(ids)):
            dupes = [x for x in ids if ids.count(x) > 1]
            msg = f"Duplicate concept_ids: {set(dupes)}"
            raise ValueError(msg)
        if len(self.categories) < 3:
            msg = f"Too few categories: {len(self.categories)} (expected >= 3)"
            raise ValueError(msg)
        return self


class AssignmentBatch(BaseModel):
    """LLM output: variable-to-archetype assignments (compact dict)."""

    assignments: dict[str, str] = Field(
        description=(
            "Map of variable_name -> archetype concept_id slug. "
            "Keys are exact variable names from input, values are "
            "concept_id slugs from the archetype list."
        )
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a biomedical data cataloger. Sort these research variables into
measurement archetypes — canonical patterns that represent the same
underlying measurement across studies and time points.

Rules:
- Each archetype = a DISTINCT measurement type
  (e.g., "atrial fibrillation" and "QT interval" are different)
- Variables with different names but the same measurement = SAME archetype
  (e.g., AFIB, ATRFIB21, ECGAFIB are all "atrial fibrillation")
- Visit/exam suffixes (V1, V2, _s1, _ex03) indicate timepoints, not
  different measurements — same archetype
- Assign EVERY variable to exactly one archetype
- Return variable names EXACTLY as given (case-sensitive)
- Aim for 5-50 archetypes. Merge tiny groups; split huge ones.
- Each archetype needs a short snake_case concept_id slug, a human-readable
  name, and a description specific enough for search matching.
"""

ASSIGN_SYSTEM_PROMPT = """\
You are a biomedical data cataloger. Assign each variable to the single
best-matching archetype from the provided list.

Rules:
- Use the variable's description (not just its name) to decide placement.
- Variables with different names but the same measurement = SAME archetype.
- Visit/exam suffixes (V1, V2, _s1, _ex03) indicate timepoints, not
  different measurements — same archetype.
- Assign EVERY variable to exactly one archetype.
- Return variable names EXACTLY as given (case-sensitive).
- Use ONLY the concept_id slugs from the archetype list provided.
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
        f"Sort these {len(variables)} variables into 5-50 measurement archetypes.\n",
        "## Variables\n",
    ]
    for v in variables:
        lines.append(f"- **{v['name']}**: {v['description']}")
    lines.append(
        "\n\nProduce the archetype tree. Remember:\n"
        "- 5-50 archetypes, each a distinct measurement type\n"
        "- Every variable must be assigned to exactly one archetype\n"
        "- Return variable names exactly as shown above"
    )
    return "\n".join(lines)


def build_assign_prompt(
    parent_concept: str,
    archetypes: list[Archetype],
    variables: list[dict],
) -> str:
    """Build a prompt to assign variables to existing archetypes.

    Args:
        parent_concept: The parent concept.
        archetypes: Archetype definitions from the first pass.
        variables: Variables to assign.

    Returns:
        Formatted user prompt string.
    """
    lines = [
        f"## Parent concept: `{parent_concept}`\n",
        "## Available archetypes\n",
    ]
    for a in archetypes:
        lines.append(f"- **{a.concept_id}**: {a.name} — {a.description}")
    lines.append(f"\n## Variables to assign ({len(variables)})\n")
    for v in variables:
        lines.append(f"- **{v['name']}**: {v['description']}")
    lines.append(
        "\n\nAssign each variable to exactly one archetype from the list above.\n"
        "Return variable names exactly as shown."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1: Discovery
# ---------------------------------------------------------------------------


def discover_large_concepts(min_vars: int) -> dict[str, int]:
    """Scan all study JSONs and count variables per concept_id.

    Args:
        min_vars: Minimum variable count to be considered "large".

    Returns:
        Dict of concept_id -> variable count, filtered to those >= min_vars.
    """
    counts: dict[str, int] = {}
    for path in sorted(LLM_DIR.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        for table in data.get("tables", []):
            for var in table.get("variables", []):
                cid = var.get("concept_id")
                if cid:
                    counts[cid] = counts.get(cid, 0) + 1

    # Filter to large concepts, exclude existing ncpi: archetypes/subconcepts
    large = {
        cid: count
        for cid, count in counts.items()
        if count >= min_vars and not cid.startswith("ncpi:")
    }
    return dict(sorted(large.items(), key=lambda x: -x[1]))


# ---------------------------------------------------------------------------
# Phase 2: Variable collection + LLM calls
# ---------------------------------------------------------------------------


def collect_variables(
    concept_id: str,
) -> tuple[list[dict], dict[str, list[tuple[str, int, int]]]]:
    """Scan v4 output and collect variables for a concept.

    Args:
        concept_id: The concept_id to collect variables for.

    Returns:
        Tuple of:
        - Deduplicated variable list: [{name, description}]
        - Location index: name_lower -> [(study_path_stem, table_idx, var_idx)]
    """
    seen: dict[tuple[str, str], dict] = {}
    locations: dict[str, list[tuple[str, int, int]]] = {}

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


def concept_id_to_prefix(concept_id: str) -> str:
    """Derive the ncpi: archetype prefix from a concept_id.

    Args:
        concept_id: Parent concept (e.g. "topmed:ecg").

    Returns:
        Prefix string (e.g. "ncpi:ecg").
    """
    bare = concept_id.split(":", 1)[-1] if ":" in concept_id else concept_id
    return f"ncpi:{bare}"


def _make_model() -> AnthropicModel:
    """Create an AnthropicModel with a long timeout.

    Returns:
        Configured AnthropicModel instance.
    """
    client = AsyncAnthropic(
        timeout=httpx.Timeout(1800.0, connect=10.0)
    )
    return AnthropicModel(
        MODEL,
        provider=AnthropicProvider(anthropic_client=client),
    )


async def _call_define_archetypes(
    concept_id: str,
    variables: list[dict],
) -> ArchetypeTree:
    """Call LLM to define archetypes and assign a batch of variables.

    Args:
        concept_id: Parent concept.
        variables: Variables to send (must fit in context).

    Returns:
        ArchetypeTree with archetype definitions and assigned variables.
    """
    agent = Agent(
        _make_model(),
        output_type=ArchetypeTree,
        system_prompt=SYSTEM_PROMPT,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            max_tokens=64000,
            temperature=0.0,
        ),
        output_retries=3,
    )
    result = await agent.run(build_user_prompt(concept_id, variables))
    return result.output


async def _call_assign_variables(
    concept_id: str,
    archetypes: list[Archetype],
    variables: list[dict],
) -> dict[str, str]:
    """Call LLM to assign variables to existing archetypes.

    Args:
        concept_id: Parent concept.
        archetypes: Archetype definitions from the first pass.
        variables: Variables to assign.

    Returns:
        Dict of variable_name -> archetype concept_id slug.
    """
    agent = Agent(
        _make_model(),
        output_type=AssignmentBatch,
        system_prompt=ASSIGN_SYSTEM_PROMPT,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            max_tokens=32768,
            temperature=0.0,
        ),
        output_retries=3,
    )
    prompt = build_assign_prompt(concept_id, archetypes, variables)
    result = await agent.run(prompt)
    return result.output.assignments


async def generate_archetypes_for_concept(
    concept_id: str,
    dry_run: bool = False,
) -> ArchetypeTree | None:
    """Generate archetypes for one parent concept.

    For concepts with <= BATCH_SIZE unique pairs, a single LLM call defines
    archetypes and assigns all variables. For larger concepts, the first call
    defines archetypes on BATCH_SIZE pairs, then subsequent calls assign
    remaining variables to those archetypes in batches.

    Args:
        concept_id: Parent concept to expand.
        dry_run: If True, print stats without calling the LLM.

    Returns:
        ArchetypeTree result, or None if dry_run or no variables.
    """
    prefix = concept_id_to_prefix(concept_id)

    print(f"\n{'=' * 60}")
    print(f"Concept: {concept_id}")
    print(f"Prefix:  {prefix}")
    print(f"{'=' * 60}\n")

    # Check cache
    cache_file = CACHE_DIR / f"{concept_id.replace(':', '_')}.json"
    if not dry_run and cache_file.exists():
        print(f"Cache hit: {cache_file.name}")
        with open(cache_file) as f:
            return ArchetypeTree.model_validate_json(f.read())

    # Collect variables
    variables, locations = collect_variables(concept_id)
    total_locs = sum(len(v) for v in locations.values())
    print(f"Unique (name, desc) pairs: {len(variables)}")
    print(f"Total variable occurrences: {total_locs}")

    if not variables:
        print("No variables found - skipping")
        return None

    needs_batching = len(variables) > BATCH_SIZE
    if needs_batching:
        remaining_count = len(variables) - BATCH_SIZE
        assign_batches = (remaining_count + ASSIGN_BATCH_SIZE - 1) // ASSIGN_BATCH_SIZE
        n_batches = 1 + assign_batches
        print(f"Batching: {n_batches} calls (1 define @ {BATCH_SIZE:,} + "
              f"{assign_batches} assign @ <={ASSIGN_BATCH_SIZE:,})")

    # Estimate tokens
    input_chars = sum(len(v["name"]) + len(v["description"]) + 10 for v in variables)
    est_input_tokens = (len(SYSTEM_PROMPT) + input_chars) // 4
    print(f"Estimated input tokens (total): ~{est_input_tokens:,}")

    if dry_run:
        return None

    # Pass 1: Define archetypes on first batch
    batch1 = variables[:BATCH_SIZE]
    print(f"\nPass 1: defining archetypes from {len(batch1):,} variables...")
    tree = await _call_define_archetypes(concept_id, batch1)
    print(f"Generated {len(tree.categories)} archetypes")

    # Pass 2+: Assign remaining variables in batches
    if needs_batching:
        remaining = variables[BATCH_SIZE:]
        batch_num = 2
        for i in range(0, len(remaining), ASSIGN_BATCH_SIZE):
            batch = remaining[i : i + ASSIGN_BATCH_SIZE]
            print(f"\nPass {batch_num}: assigning {len(batch):,} variables "
                  f"to existing archetypes...")
            assignments = await _call_assign_variables(
                concept_id, tree.categories, batch
            )
            # Merge assignments into the tree
            valid_ids = {c.concept_id for c in tree.categories}
            for vname, arch_id in assignments.items():
                if arch_id in valid_ids:
                    # Find the archetype and append
                    for cat in tree.categories:
                        if cat.concept_id == arch_id:
                            cat.variables.append(vname)
                            break
            assigned_count = sum(1 for a in assignments.values() if a in valid_ids)
            invalid_count = len(assignments) - assigned_count
            print(f"  Assigned {assigned_count}, "
                  f"invalid archetype IDs: {invalid_count}")
            batch_num += 1

    # Validate assignment coverage
    all_input_names = {v["name"] for v in variables}
    assigned_names: set[str] = set()
    for cat in tree.categories:
        assigned_names.update(cat.variables)

    missing = all_input_names - assigned_names
    extra = assigned_names - all_input_names
    if missing:
        print(f"\nWARNING: {len(missing)} variables not assigned to any archetype")
        for m in sorted(missing)[:10]:
            print(f"  {m}")
    if extra:
        print(f"\nWARNING: {len(extra)} variable names not in input (typos?)")
        for e in sorted(extra)[:10]:
            print(f"  {e}")

    assigned_pct = len(assigned_names & all_input_names) / len(all_input_names) * 100
    print(f"\nAssignment rate: {assigned_pct:.1f}% "
          f"({len(assigned_names & all_input_names)}/{len(all_input_names)})")

    # Cache result
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        f.write(tree.model_dump_json(indent=2))
    print(f"Cached result to {cache_file.name}")

    return tree


# ---------------------------------------------------------------------------
# Phase 3: Write outputs
# ---------------------------------------------------------------------------


def write_outputs(
    results: dict[str, ArchetypeTree],
) -> None:
    """Write all archetype outputs in a single pass.

    Args:
        results: Map of concept_id -> ArchetypeTree from LLM.
    """
    if not results:
        print("\nNo results to write.")
        return

    # Load existing data
    with open(VOCAB_PATH) as f:
        vocab = json.load(f)
    with open(ISA_PATH) as f:
        isa = json.load(f)

    existing_vocab_ids = {e["concept_id"] for e in vocab}
    existing_isa_pairs = {(e["child"], e["parent"]) for e in isa}

    # Look up parent domains from vocabulary
    vocab_by_id: dict[str, dict] = {}
    for entry in vocab:
        vocab_by_id[entry["concept_id"]] = entry

    new_vocab_count = 0
    new_isa_count = 0

    # Build global var -> archetype mapping for re-tagging
    retag_map: dict[str, dict[str, str]] = {}  # concept_id -> {name_lower: full_archetype_id}

    for concept_id, tree in results.items():
        prefix = concept_id_to_prefix(concept_id)

        # Resolve parent domain
        bare_parent = concept_id.split(":", 1)[-1] if ":" in concept_id else concept_id
        parent_entry = vocab_by_id.get(bare_parent) or vocab_by_id.get(concept_id)
        domain = parent_entry["domain"] if parent_entry else "unknown"

        concept_retag: dict[str, str] = {}

        for cat in tree.categories:
            full_id = f"{prefix}_{cat.concept_id}"

            # Vocab entry (stored with ncpi: prefix)
            if full_id not in existing_vocab_ids:
                vocab.append({
                    "concept_id": full_id,
                    "cui": None,
                    "description": cat.description,
                    "domain": domain,
                    "example_variables": cat.variables[:5],
                    "name": cat.name,
                })
                existing_vocab_ids.add(full_id)
                new_vocab_count += 1

            # ISA edge: archetype -> parent
            pair = (full_id, concept_id)
            if pair not in existing_isa_pairs:
                isa.append({"child": full_id, "parent": concept_id})
                existing_isa_pairs.add(pair)
                new_isa_count += 1

            # Retag mapping
            for vname in cat.variables:
                concept_retag[vname.lower()] = full_id

        retag_map[concept_id] = concept_retag

    # Write vocab and ISA
    with open(VOCAB_PATH, "w") as f:
        json.dump(vocab, f, indent=2)
    print(f"\nAppended {new_vocab_count} entries to {VOCAB_PATH.name}")

    with open(ISA_PATH, "w") as f:
        json.dump(isa, f, indent=2)
    print(f"Appended {new_isa_count} ISA rows to {ISA_PATH.name}")

    # Re-tag study JSONs (single pass through all files)
    retag_total = 0
    files_modified = 0
    target_concepts = set(retag_map.keys())

    for path in sorted(LLM_DIR.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        modified = False
        for table in data.get("tables", []):
            for var in table.get("variables", []):
                cid = var.get("concept_id")
                if cid not in target_concepts:
                    continue
                name = var.get("name", "")
                new_id = retag_map[cid].get(name.lower())
                if new_id:
                    var["concept_id"] = new_id
                    modified = True
                    retag_total += 1
        if modified:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            files_modified += 1

    print(f"Re-tagged {retag_total:,} variable occurrences in {files_modified} study files")

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    for concept_id, tree in sorted(results.items()):
        prefix = concept_id_to_prefix(concept_id)
        total_vars = sum(len(c.variables) for c in tree.categories)
        print(f"\n{concept_id} -> {len(tree.categories)} archetypes ({total_vars} vars)")
        for cat in sorted(tree.categories, key=lambda c: -len(c.variables)):
            print(f"  {prefix}_{cat.concept_id}: {cat.name} ({len(cat.variables)} vars)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> None:
    """Run archetype generation.

    Args:
        args: Parsed command-line arguments.
    """
    min_vars = args.min_vars

    if args.concept:
        # Single concept mode — don't require it to meet the threshold
        large = {args.concept: 0}
    else:
        # Discovery: find all large concepts
        large = discover_large_concepts(min_vars)

    if not large:
        print(f"No concepts found with >= {min_vars} variables.")
        return

    # Report
    print(f"Found {len(large)} concepts with >= {min_vars} variables:")
    total_vars = 0
    for cid, count in large.items():
        print(f"  {cid}: {count:,} vars")
        total_vars += count
    print(f"\nTotal variables to process: {total_vars:,}")

    est_cost = len(large) * 0.08  # rough estimate per concept
    print(f"Estimated Sonnet cost: ~${est_cost:.0f}")

    if args.dry_run:
        print("\n--- Dry run: collecting per-concept stats ---")

    # Process each concept
    results: dict[str, ArchetypeTree] = {}
    failed: list[str] = []
    for concept_id in large:
        try:
            tree = await generate_archetypes_for_concept(concept_id, dry_run=args.dry_run)
            if tree:
                results[concept_id] = tree
        except Exception as exc:
            print(f"\nERROR processing {concept_id}: {exc}")
            failed.append(concept_id)

    if failed:
        print(f"\n{'=' * 60}")
        print(f"FAILED concepts ({len(failed)}) — re-run to retry:")
        for cid in failed:
            print(f"  {cid}")
        print(f"{'=' * 60}")

    if not args.dry_run:
        write_outputs(results)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Generate variable archetypes for large concepts"
    )
    parser.add_argument(
        "--concept", type=str, help="Specific concept_id to process"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show stats without calling LLM"
    )
    parser.add_argument(
        "--min-vars",
        type=int,
        default=DEFAULT_MIN_VARS,
        help=f"Minimum variable count threshold (default: {DEFAULT_MIN_VARS})",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
