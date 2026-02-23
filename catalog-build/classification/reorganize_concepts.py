"""Reorganize concept hierarchy: merge synonyms + build variable-depth tree.

Takes the existing v1 concept hierarchy (concept-hierarchy.json) and for
each mid-level category, uses two LLM passes:
1. Find synonyms — which input concepts mean the same thing? No renaming.
2. Build is_a tree — which concepts are children of others? No renaming.

Output validators ensure no input concepts are dropped. The LLM must use
exact input names (no rewriting/renaming).

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python reorganize_concepts.py                           # All mid-levels
    python reorganize_concepts.py --domain Cardiovascular   # One domain
    python reorganize_concepts.py --mid-level "Blood Pressure" --domain Cardiovascular
    python reorganize_concepts.py --debug                   # Verbose output
    python reorganize_concepts.py --dry-run                 # Show what would be processed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Clear Claude Code sandbox proxy vars — they interfere with httpx/Anthropic API calls
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from dataclasses import dataclass

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.settings import ModelSettings

from models import (
    ConceptNode,
    SynonymMapping,
    SynonymOnlyResult,
    TreeOnlyResult,
    _collect_tree_concepts,
    build_tree_from_placements,
    find_single_child_nodes,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

V1_HIERARCHY_PATH = SCRIPT_DIR / "output" / "concept-hierarchy.json"
V2_OUTPUT_DIR = SCRIPT_DIR / "output" / "v2"
V2_HIERARCHY_PATH = V2_OUTPUT_DIR / "concept-hierarchy-v2.json"
SYNONYM_MAP_PATH = V2_OUTPUT_DIR / "synonym-map.json"

MODEL = "anthropic:claude-haiku-4-5-20251001"
MAX_RETRIES = 5
DEFAULT_CONCURRENCY = 10
DEBUG = False

# ---------------------------------------------------------------------------
# System prompts — simple, focused, no renaming
# ---------------------------------------------------------------------------

SYNONYM_SYSTEM_PROMPT = """\
You find synonym pairs in medical/clinical concept lists.

Given a list of concept names, find pairs that refer to the exact same
measurement but use different wording. Map the less common name to the
more common one.

Rules:
- Only merge concepts that truly mean the SAME measurement.
  "Sitting Diastolic BP" and "Seated Diastolic BP" → synonyms.
  "Systolic BP" and "Diastolic BP" → NOT synonyms (different measurements).
- Both the `synonym` and `canonical` must be EXACT names from the input list.
  Do NOT rename, rewrite, or fix casing. Use the input names exactly as given.
- Prefer the name with the higher study count as canonical.
- If no synonyms exist, return an empty list.
"""

TREE_SYSTEM_PROMPT = """\
You organize medical/clinical concepts into is_a hierarchies.

Given a list of concept names, figure out which are children of others and
assign parent references. Output a flat list of concept-parent pairs.

Rules:
- A child is a MORE SPECIFIC TYPE of its parent. Set parent to null for roots.
  "Standing Systolic Blood Pressure" is_a "Systolic Blood Pressure".
- Use the EXACT concept names from the input. Do NOT rename or rewrite them.
- You MAY create new grouping parent nodes not in the input (e.g. "Cranial
  Measurements" to group "Head Circumference" and "Cranial Length"), but every
  new node must have at least 2 children.
- If concepts are peers (equally specific), give them the same parent.
- The hierarchy can be any depth as the domain requires.
"""

# ---------------------------------------------------------------------------
# Load v1 hierarchy
# ---------------------------------------------------------------------------


def load_v1_hierarchy(path: Path) -> dict:
    """Load the v1 concept hierarchy JSON.

    Args:
        path: Path to concept-hierarchy.json.

    Returns:
        Parsed hierarchy dict with 'concepts' and 'hierarchy' keys.
    """
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Agent deps — carries input concepts for output validation
# ---------------------------------------------------------------------------


@dataclass
class ReorgDeps:
    """Dependencies passed to agents for output validation."""

    input_concepts: set[str]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def make_synonym_agent(model: str) -> Agent[ReorgDeps, SynonymOnlyResult]:
    """Create the synonym-detection agent.

    Args:
        model: Model identifier string.

    Returns:
        Configured pydantic-ai Agent.
    """
    agent: Agent[ReorgDeps, SynonymOnlyResult] = Agent(
        model,
        deps_type=ReorgDeps,
        output_type=SynonymOnlyResult,
        system_prompt=SYNONYM_SYSTEM_PROMPT,
        retries=5,
        model_settings=ModelSettings(temperature=0.0),
    )

    @agent.output_validator
    def check_synonyms(
        ctx: RunContext[ReorgDeps], result: SynonymOnlyResult
    ) -> SynonymOnlyResult:
        input_names = ctx.deps.input_concepts
        for s in result.synonyms:
            if s.synonym not in input_names:
                raise ModelRetry(
                    f"Synonym '{s.synonym}' is not in the input list. "
                    f"Use exact input names only."
                )
            if s.canonical not in input_names:
                raise ModelRetry(
                    f"Canonical '{s.canonical}' is not in the input list. "
                    f"Use exact input names only."
                )
        return result

    return agent


def make_tree_agent(model: str) -> Agent[ReorgDeps, TreeOnlyResult]:
    """Create the tree-building agent.

    Args:
        model: Model identifier string.

    Returns:
        Configured pydantic-ai Agent.
    """
    agent: Agent[ReorgDeps, TreeOnlyResult] = Agent(
        model,
        deps_type=ReorgDeps,
        output_type=TreeOnlyResult,
        system_prompt=TREE_SYSTEM_PROMPT,
        retries=5,
        model_settings=ModelSettings(temperature=0.0),
    )

    @agent.output_validator
    def check_tree(
        ctx: RunContext[ReorgDeps], result: TreeOnlyResult
    ) -> TreeOnlyResult:
        output_concepts = result.get_all_concepts()
        missing = ctx.deps.input_concepts - output_concepts
        if missing:
            raise ModelRetry(
                f"You dropped {len(missing)} input concepts. Every input "
                f"concept must appear in `concepts`. "
                f"Missing: {sorted(missing)}"
            )
        return result

    return agent


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_synonym_prompt(
    domain: str,
    mid_level: str,
    concepts: list[dict],
) -> str:
    """Format the user prompt for synonym detection.

    Args:
        domain: Top-level domain name.
        mid_level: Mid-level category name.
        concepts: List of dicts with 'concept' and 'study_count' keys.

    Returns:
        Formatted prompt string.
    """
    concept_lines = "\n".join(
        f"- {c['concept']} ({c['study_count']} studies)" for c in concepts
    )
    return (
        f"Domain: {domain}\n"
        f"Mid-level category: {mid_level}\n\n"
        f"Find synonym pairs among these {len(concepts)} concepts.\n"
        f"Use exact input names only — no renaming.\n\n"
        f"{concept_lines}"
    )


def format_tree_prompt(
    domain: str,
    mid_level: str,
    concepts: list[dict],
) -> str:
    """Format the user prompt for tree building.

    Args:
        domain: Top-level domain name.
        mid_level: Mid-level category name.
        concepts: List of dicts with 'concept' and 'study_count' keys.

    Returns:
        Formatted prompt string.
    """
    concept_lines = "\n".join(
        f"- {c['concept']} ({c['study_count']} studies)" for c in concepts
    )
    return (
        f"Domain: {domain}\n"
        f"Mid-level category: {mid_level}\n\n"
        f"Build an is_a tree for these {len(concepts)} concepts.\n"
        f"Use exact input names — no renaming. You may create grouping\n"
        f"parent nodes (with 2+ children) if needed.\n\n"
        f"{concept_lines}"
    )


# ---------------------------------------------------------------------------
# LLM call with rate-limit retry
# ---------------------------------------------------------------------------


async def _run_agent(
    agent: Agent,
    prompt: str,
    label: str,
    deps: ReorgDeps | None = None,
) -> object | None:
    """Run an agent with rate-limit retry.

    Args:
        agent: The pydantic-ai Agent to run.
        prompt: User prompt string.
        label: Human-readable label for logging.
        deps: Optional deps for output validation.

    Returns:
        Agent output or None on failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await agent.run(prompt, deps=deps)
            if DEBUG:
                usage = result.usage()
                print(
                    f"      {label}: "
                    f"{usage.input_tokens} in / {usage.output_tokens} out",
                    file=sys.stderr,
                )
            return result.output
        except ModelHTTPError as e:
            if e.status_code == 429 and attempt < MAX_RETRIES:
                wait = 2**attempt
                print(
                    f"    Rate limited ({label}), retrying in {wait}s "
                    f"(attempt {attempt}/{MAX_RETRIES})...",
                    file=sys.stderr,
                )
                await asyncio.sleep(wait)
            else:
                print(f"    ERROR [{label}]: {e}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"    ERROR [{label}]: {e}", file=sys.stderr)
            return None
    return None


# ---------------------------------------------------------------------------
# Process one mid-level (two-pass: synonyms then tree)
# ---------------------------------------------------------------------------


async def process_midlevel(
    synonym_agent: Agent[ReorgDeps, SynonymOnlyResult],
    tree_agent: Agent[ReorgDeps, TreeOnlyResult],
    domain: str,
    mid_level: str,
    concepts: list[dict],
) -> tuple[list[ConceptNode], list[SynonymMapping]] | None:
    """Process a mid-level in two LLM calls.

    Pass 1: Find synonyms (no renaming, exact input names).
    Pass 2: Build is_a tree from de-duplicated concepts.

    Args:
        synonym_agent: Agent for synonym detection.
        tree_agent: Agent for tree building.
        domain: Top-level domain name.
        mid_level: Mid-level category name.
        concepts: List of concept dicts.

    Returns:
        Tuple of (tree_nodes, synonyms) or None on error.
    """
    input_set = {c["concept"] for c in concepts}

    # Pass 1: Synonym detection
    prompt1 = format_synonym_prompt(domain, mid_level, concepts)
    syn_deps = ReorgDeps(input_concepts=input_set)
    syn_result: SynonymOnlyResult | None = await _run_agent(
        synonym_agent, prompt1, f"{mid_level}/synonyms", deps=syn_deps
    )
    if syn_result is None:
        return None

    syn_map = {s.synonym: s.canonical for s in syn_result.synonyms}
    if DEBUG and syn_map:
        print(
            f"      Pass 1: {len(syn_map)} synonyms found",
            file=sys.stderr,
        )

    # De-duplicate: keep concepts that are not synonym sources
    deduped = [c for c in concepts if c["concept"] not in syn_map]

    # Pass 2: Tree building on de-duplicated concepts
    prompt2 = format_tree_prompt(domain, mid_level, deduped)
    tree_deps = ReorgDeps(input_concepts={c["concept"] for c in deduped})
    tree_result: TreeOnlyResult | None = await _run_agent(
        tree_agent, prompt2, f"{mid_level}/tree", deps=tree_deps
    )
    if tree_result is None:
        return None

    return tree_result.build_tree(), list(syn_result.synonyms)


# ---------------------------------------------------------------------------
# Build output hierarchy
# ---------------------------------------------------------------------------


def tree_to_hierarchy_dict(
    nodes: list[ConceptNode],
    concept_counts: dict[str, int],
) -> list[dict]:
    """Convert ConceptNode list to serializable hierarchy dicts.

    Args:
        nodes: List of ConceptNode objects.
        concept_counts: Concept name -> study count lookup.

    Returns:
        List of serializable hierarchy entry dicts.
    """
    result = []
    for node in nodes:
        entry = {
            "concept": node.concept,
            "studyCount": concept_counts.get(node.concept, 0),
        }
        if node.children:
            entry["children"] = tree_to_hierarchy_dict(
                node.children, concept_counts
            )
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def reorganize(
    domain_filter: str | None = None,
    midlevel_filter: str | None = None,
    model: str = MODEL,
    dry_run: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> None:
    """Run the concept reorganization pipeline.

    Args:
        domain_filter: Only process this domain (optional).
        midlevel_filter: Only process this mid-level (optional).
        model: Model identifier.
        dry_run: If True, just show what would be processed.
        concurrency: Max concurrent LLM calls.
    """
    print("Loading v1 hierarchy...", file=sys.stderr)
    v1 = load_v1_hierarchy(V1_HIERARCHY_PATH)
    hierarchy = v1["hierarchy"]
    concept_info = v1["concepts"]

    # Build concept -> study_count lookup
    concept_counts = {c: info["study_count"] for c, info in concept_info.items()}

    # Collect mid-levels to process
    work: list[tuple[str, str, list[dict]]] = []
    for domain in sorted(hierarchy.keys()):
        if domain_filter and domain != domain_filter:
            continue
        for mid_level in sorted(hierarchy[domain].keys()):
            if midlevel_filter and mid_level != midlevel_filter:
                continue
            concepts = hierarchy[domain][mid_level]
            work.append((domain, mid_level, concepts))

    total_concepts = sum(len(c) for _, _, c in work)
    print(
        f"  {len(work)} mid-levels, {total_concepts} concepts to process\n"
        f"  Concurrency: {concurrency}",
        file=sys.stderr,
    )

    if dry_run:
        for domain, mid_level, concepts in work:
            print(
                f"  {domain} / {mid_level}: "
                f"{len(concepts)} concepts"
            )
        return

    # Create agents
    synonym_agent = make_synonym_agent(model)
    tree_agent = make_tree_agent(model)
    semaphore = asyncio.Semaphore(concurrency)
    start = time.time()
    progress_counter = {"done": 0}

    async def process_one(
        idx: int,
        domain: str,
        mid_level: str,
        concepts: list[dict],
    ) -> tuple[str, str, list[dict], list[ConceptNode] | None, list[SynonymMapping]]:
        """Process a single mid-level (with semaphore).

        Args:
            idx: 1-based index for progress logging.
            domain: Top-level domain name.
            mid_level: Mid-level category name.
            concepts: List of concept dicts.

        Returns:
            Tuple of (domain, mid_level, concepts, tree_nodes, synonyms).
            tree_nodes is None for skip, empty list for error.
        """
        n = len(concepts)

        if n <= 1:
            return (domain, mid_level, concepts, None, [])

        async with semaphore:
            print(
                f"  [{idx}/{len(work)}] {domain} / {mid_level} "
                f"({n} concepts)...",
                file=sys.stderr,
            )

            result = await process_midlevel(
                synonym_agent, tree_agent, domain, mid_level, concepts
            )

            progress_counter["done"] += 1
            if result is None:
                print(
                    f"    FAILED [{mid_level}] "
                    f"({progress_counter['done']}/{len(work)} done)",
                    file=sys.stderr,
                )
                return (domain, mid_level, concepts, [], [])

            tree_nodes, synonyms = result
            return (domain, mid_level, concepts, tree_nodes, synonyms)

    # Launch all tasks concurrently (semaphore limits actual parallelism)
    tasks = [
        process_one(i, domain, mid_level, concepts)
        for i, (domain, mid_level, concepts) in enumerate(work, 1)
    ]
    results = await asyncio.gather(*tasks)

    # Collect results
    all_synonyms: dict[str, str] = {}
    v2_hierarchy: dict[str, dict[str, list[dict]]] = {}
    v2_concepts: dict[str, dict] = {}
    processed = 0
    errors = 0

    for domain, mid_level, concepts, tree_nodes, synonyms in results:
        n = len(concepts)

        if n <= 1:
            # Single concept — no reorganization needed
            if domain not in v2_hierarchy:
                v2_hierarchy[domain] = {}
            v2_hierarchy[domain][mid_level] = [
                {
                    "concept": c["concept"],
                    "studyCount": c["study_count"],
                }
                for c in concepts
            ]
            for c in concepts:
                v2_concepts[c["concept"]] = {
                    "domain": domain,
                    "midLevel": mid_level,
                    "studyCount": c["study_count"],
                }
            processed += 1
            continue

        if tree_nodes is not None and len(tree_nodes) == 0:
            # Error sentinel — fallback to flat
            errors += 1
            if domain not in v2_hierarchy:
                v2_hierarchy[domain] = {}
            v2_hierarchy[domain][mid_level] = [
                {
                    "concept": c["concept"],
                    "studyCount": c["study_count"],
                }
                for c in concepts
            ]
            for c in concepts:
                v2_concepts[c["concept"]] = {
                    "domain": domain,
                    "midLevel": mid_level,
                    "studyCount": c["study_count"],
                }
            continue

        # Collect tree concepts
        tree_concept_set: set[str] = set()
        _collect_tree_concepts(tree_nodes, tree_concept_set)

        # Log results
        input_concepts = {c["concept"] for c in concepts}
        n_tree = len(tree_concept_set)
        n_syn = len(synonyms)
        n_invented = len(tree_concept_set - input_concepts)
        single_child = find_single_child_nodes(tree_nodes)
        sc_note = f", {len(single_child)} single-child" if single_child else ""
        inv_note = f", {n_invented} invented" if n_invented else ""
        print(
            f"    {mid_level}: {n_tree} tree nodes"
            f"({inv_note}{sc_note}), {n_syn} synonyms",
            file=sys.stderr,
        )

        # Collect synonyms
        for s in synonyms:
            all_synonyms[s.synonym] = s.canonical

        # Build hierarchy entry
        if domain not in v2_hierarchy:
            v2_hierarchy[domain] = {}
        v2_hierarchy[domain][mid_level] = tree_to_hierarchy_dict(
            tree_nodes, concept_counts
        )

        # Build per-concept lookup
        for concept_name in tree_concept_set:
            v2_concepts[concept_name] = {
                "domain": domain,
                "midLevel": mid_level,
                "studyCount": concept_counts.get(concept_name, 0),
            }

        processed += 1

    elapsed = time.time() - start
    print(
        f"\nDone in {elapsed:.0f}s. "
        f"{processed}/{len(work)} mid-levels processed "
        f"({errors} errors). "
        f"{len(all_synonyms)} synonyms merged. "
        f"{len(v2_concepts)} canonical concepts.",
        file=sys.stderr,
    )

    # Save outputs
    V2_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save hierarchy
    output = {
        "concepts": v2_concepts,
        "hierarchy": v2_hierarchy,
        "stats": {
            "domains": len(v2_hierarchy),
            "midLevels": sum(len(m) for m in v2_hierarchy.values()),
            "synonymsMerged": len(all_synonyms),
            "totalConcepts": len(v2_concepts),
        },
    }
    with open(V2_HIERARCHY_PATH, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    print(f"Hierarchy: {V2_HIERARCHY_PATH}", file=sys.stderr)

    # Save synonym map
    with open(SYNONYM_MAP_PATH, "w") as f:
        json.dump(
            {"mapping": all_synonyms, "count": len(all_synonyms)},
            f,
            indent=2,
        )
        f.write("\n")
    print(f"Synonym map: {SYNONYM_MAP_PATH}", file=sys.stderr)

    print(
        f"\nStats: {output['stats']}",
        file=sys.stderr,
    )


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Reorganize concept hierarchy: synonym merge + tree building"
    )
    parser.add_argument(
        "--domain",
        help="Only process this domain (e.g. Cardiovascular)",
    )
    parser.add_argument(
        "--mid-level",
        help="Only process this mid-level (requires --domain)",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Model to use (default: {MODEL})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent LLM calls (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without calling LLM",
    )
    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    if args.mid_level and not args.domain:
        parser.error("--mid-level requires --domain")

    asyncio.run(
        reorganize(
            domain_filter=args.domain,
            midlevel_filter=args.mid_level,
            model=args.model,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
