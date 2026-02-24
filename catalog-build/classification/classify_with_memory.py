"""Tabula rasa variable classification with a growing concept bank.

Classifies dbGaP variables into standardized concept names, maintaining a
growing bank of previously-assigned concepts so the LLM reuses consistent
names across studies. Studies are processed largest-first so common
measurements seed the bank early.

This is Step 1 of the v2 pipeline:
  1. classify_with_memory.py   -> concept name per variable (this script)
  2. build_concept_hierarchy.py pass 1 -> domain per concept
  3. build_concept_hierarchy.py pass 2 -> mid-level per concept
  4. reorganize_concepts.py    -> synonyms + is_a tree

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python classify_with_memory.py                      # All studies, tabula rasa
    python classify_with_memory.py --study phs000007    # Single study
    python classify_with_memory.py --debug --dry-run    # Preview what would run
    python classify_with_memory.py --bank-size 1000     # Top N concepts in prompt
    python classify_with_memory.py --concurrency 10     # Concurrent tables per study
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Clear Claude Code sandbox proxy vars — they interfere with httpx/Anthropic API calls
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from models import ClassifiedBatch, ParsedTable
from parse_var_reports import CACHE_FILE, load_cache

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

CONCEPT_PROMPT_PATH = SCRIPT_DIR / "CONCEPT_PROMPT.md"
V2_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts-v2"
BANK_PATH = SCRIPT_DIR / "output" / "v2" / "concept-bank.json"

# ---------------------------------------------------------------------------
# Configuration (overridable via CLI args)
# ---------------------------------------------------------------------------

MODEL = "anthropic:claude-haiku-4-5"
DEBUG = False
VARS_PER_BATCH = 100
MAX_RETRIES = 5
DEFAULT_CONCURRENCY = 10
DEFAULT_BANK_SIZE = 1000
NEEDS_REVIEW_CONCEPT = "Needs Review"


# ---------------------------------------------------------------------------
# Concept Bank
# ---------------------------------------------------------------------------


@dataclass
class ConceptBank:
    """Growing concept registry that tracks assigned names and their frequency."""

    concepts: dict[str, int] = field(default_factory=dict)

    def top_n(self, n: int = DEFAULT_BANK_SIZE) -> list[tuple[str, int]]:
        """Return top N concepts by variable count.

        Args:
            n: Maximum number of concepts to return.

        Returns:
            List of (concept_name, count) tuples sorted by count descending.
        """
        sorted_items = sorted(self.concepts.items(), key=lambda x: -x[1])
        return sorted_items[:n]

    def format_for_prompt(self, n: int = DEFAULT_BANK_SIZE) -> str:
        """Format top concepts for inclusion in the LLM system prompt.

        Args:
            n: Maximum number of concepts to include.

        Returns:
            Formatted string listing concepts with counts.
        """
        top = self.top_n(n)
        if not top:
            return "No concepts assigned yet. Assign clean Title Case names."
        lines = [f"{name} ({count})" for name, count in top]
        return ", ".join(lines)

    def register(self, concepts: list[str]) -> int:
        """Add or increment concept counts.

        Args:
            concepts: List of concept names to register.

        Returns:
            Number of newly created concepts (not previously in the bank).
        """
        new_count = 0
        for name in concepts:
            if name not in self.concepts:
                new_count += 1
                self.concepts[name] = 0
            self.concepts[name] += 1
        return new_count

    def save(self, path: Path) -> None:
        """Persist bank to JSON.

        Args:
            path: Output file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "totalConcepts": len(self.concepts),
            "concepts": dict(sorted(self.concepts.items(), key=lambda x: -x[1])),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    @classmethod
    def load(cls, path: Path) -> ConceptBank:
        """Load bank from JSON.

        Args:
            path: Input file path.

        Returns:
            Loaded ConceptBank instance.
        """
        with open(path) as f:
            data = json.load(f)
        return cls(concepts=data.get("concepts", {}))


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------


def _normalize_concept(name: str) -> str:
    """Normalize a concept name for near-duplicate comparison.

    Strips to lowercase alphanumeric + spaces, collapses whitespace.
    "Systolic Blood-Pressure" and "Systolic Blood Pressure" both become
    "systolic blood pressure".

    Args:
        name: Concept name to normalize.

    Returns:
        Normalized string for comparison.
    """
    import re as _re

    lowered = name.lower()
    alpha_only = _re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(alpha_only.split())


def _build_bank_lookup(bank: ConceptBank) -> dict[str, str]:
    """Build a normalized-concept → original-name lookup for dupe detection.

    Args:
        bank: Current concept bank.

    Returns:
        Dict mapping normalized concept strings to their original bank names.
    """
    lookup: dict[str, str] = {}
    for name in bank.concepts:
        norm = _normalize_concept(name)
        # Keep the first (highest-count) entry if two bank concepts collide
        if norm not in lookup:
            lookup[norm] = name
    return lookup


# ---------------------------------------------------------------------------
# Deps for output validation
# ---------------------------------------------------------------------------


@dataclass
class ClassifyDeps:
    """Dependencies passed to the agent for output validation."""

    bank_lookup: dict[str, str]  # normalized_concept → original bank name
    input_variable_names: set[str]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt(bank: ConceptBank, bank_size: int) -> str:
    """Build the system prompt with concept naming rules and bank context.

    Args:
        bank: Current concept bank.
        bank_size: Max concepts to include from the bank.

    Returns:
        Complete system prompt string.
    """
    prompt_md = CONCEPT_PROMPT_PATH.read_text()
    instructions = """
## Your Task

You will receive a table from a dbGaP study with its name, description, and
a list of variables (name + description). Assign a concept to EVERY variable.

**Instructions:**

1. For each variable, work through the reasoning questions above before naming.
   Capture your reasoning in the "reasoning" field.
2. Return one entry per variable, using the exact variable name from the input.
3. Use the table name and description as context — they tell you what instrument
   or procedure produced the data, which helps disambiguate opaque variable names.
   But do NOT let the table name override what the variable itself measures.
4. When multiple variables clearly measure the same thing (e.g. SBP reading 1,
   SBP reading 2), they must get the same concept name.
5. Prefer reusing concept names from the bank below over inventing new ones.
6. If you cannot confidently answer the reasoning questions, assign "Needs Review".
"""

    bank_section = f"""
## Previously Assigned Concepts

Reuse these EXACT names when a variable measures the same thing.
Only create a new name when nothing here matches.

{bank.format_for_prompt(bank_size)}
"""
    return prompt_md + "\n" + instructions + "\n" + bank_section


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def make_agent(
    bank: ConceptBank, bank_size: int
) -> Agent[ClassifyDeps, ClassifiedBatch]:
    """Create the classification agent with current bank context.

    Args:
        bank: Current concept bank.
        bank_size: Max concepts to include in prompt.

    Returns:
        Configured pydantic-ai Agent.
    """
    agent: Agent[ClassifyDeps, ClassifiedBatch] = Agent(
        MODEL,
        deps_type=ClassifyDeps,
        output_type=ClassifiedBatch,
        system_prompt=build_system_prompt(bank, bank_size),
        retries=3,
        model_settings={
            "anthropic_cache_instructions": True,
            "max_tokens": 16384,
            "temperature": 0.0,
        },
    )

    @agent.output_validator
    async def validate_completeness(
        ctx: RunContext[ClassifyDeps], result: ClassifiedBatch
    ) -> ClassifiedBatch:
        """Ensure every input variable is classified, no extras, no near-dupe concepts.

        Args:
            ctx: Run context with input variable names and bank lookup.
            result: LLM output to validate.

        Returns:
            Validated result.
        """
        output_vars = {v.variable_name for v in result.variables}
        missing = ctx.deps.input_variable_names - output_vars
        if missing:
            msg = f"Missing {len(missing)} variables: {sorted(missing)[:5]}"
            print(f"    RETRY: {msg}", file=sys.stderr)
            raise ModelRetry(msg)
        extra = output_vars - ctx.deps.input_variable_names
        if extra:
            msg = f"Extra variables not in input: {sorted(extra)[:5]}"
            print(f"    RETRY: {msg}", file=sys.stderr)
            raise ModelRetry(msg)

        # Check for near-duplicate concepts against the bank
        bank_lookup = ctx.deps.bank_lookup
        bank_exact = set(bank_lookup.values())
        near_dupes: list[str] = []
        for v in result.variables:
            if v.concept in bank_exact:
                continue  # exact match — good
            norm = _normalize_concept(v.concept)
            if norm in bank_lookup:
                near_dupes.append(
                    f"'{v.concept}' -> use '{bank_lookup[norm]}'"
                )
        if near_dupes:
            msg = (
                f"Near-duplicate concepts found. Use the existing bank "
                f"name instead: {'; '.join(near_dupes[:5])}"
            )
            print(f"    RETRY: {msg}", file=sys.stderr)
            raise ModelRetry(msg)

        return result

    return agent


# ---------------------------------------------------------------------------
# User message formatting (same structure as v1)
# ---------------------------------------------------------------------------


def format_table_prompt(
    study_id: str,
    study_name: str,
    table: ParsedTable,
    variables: list[dict[str, str]] | None = None,
) -> str:
    """Format a table's variables into the user message sent to the agent.

    Args:
        study_id: The study accession (e.g. phs000007).
        study_name: Human-readable study name.
        table: The ParsedTable for context (name, description).
        variables: Subset of variables to include (defaults to all).

    Returns:
        Formatted string with the table's metadata and variables.
    """
    desc = table.description if table.description else "(none)"
    vars_to_show = variables if variables is not None else table.variables

    var_lines = []
    for v in vars_to_show:
        name = v["name"]
        d = v.get("description")
        var_lines.append(f"  {name}: {d}" if d else f"  {name}")
    vars_block = "\n".join(var_lines)

    return (
        f"Study: {study_id} — {study_name}\n\n"
        f"TABLE: {table.table_name}  ({len(vars_to_show):,} vars)\n"
        f"DESCRIPTION: {desc}\n"
        f"VARIABLES:\n{vars_block}"
    )


# ---------------------------------------------------------------------------
# Classify a batch of variables (with retry)
# ---------------------------------------------------------------------------


async def classify_batch(
    agent: Agent[ClassifyDeps, ClassifiedBatch],
    bank_lookup: dict[str, str],
    study_id: str,
    study_name: str,
    table: ParsedTable,
    variables: list[dict[str, str]],
) -> tuple[ClassifiedBatch, int, int]:
    """Run the agent on a batch of variables with retry on rate-limit errors.

    Args:
        agent: The classification agent.
        bank_lookup: Normalized concept → original bank name for dupe detection.
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table (for context).
        variables: The variable subset to classify.

    Returns:
        Tuple of (ClassifiedBatch, input_tokens, output_tokens).
    """
    prompt = format_table_prompt(study_id, study_name, table, variables)
    input_names = {v["name"] for v in variables}
    deps = ClassifyDeps(bank_lookup=bank_lookup, input_variable_names=input_names)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await agent.run(prompt, deps=deps)
            usage = result.usage()
            if DEBUG:
                concepts_str = "\n".join(
                    f"    {vc.variable_name}: {vc.concept}"
                    for vc in result.output.variables
                )
                print(
                    f"\n{'─'*60}\n"
                    f"REQUEST  [{table.table_name}] ({len(variables)} vars)\n{prompt}\n"
                    f"{'─'*60}\n"
                    f"RESPONSE [{table.table_name}]\n"
                    f"  reasoning: {result.output.reasoning}\n"
                    f"{concepts_str}\n"
                    f"  tokens: {usage.input_tokens} in / {usage.output_tokens} out\n"
                    f"{'─'*60}",
                    file=sys.stderr,
                )
            return result.output, usage.input_tokens, usage.output_tokens
        except ModelHTTPError as e:
            if e.status_code == 429 and attempt < MAX_RETRIES:
                wait = 2**attempt
                print(
                    f"    Rate limited, retrying in {wait}s "
                    f"(attempt {attempt}/{MAX_RETRIES})...",
                    file=sys.stderr,
                )
                await asyncio.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Classify all variables in a table (chunking into batches)
# ---------------------------------------------------------------------------


async def classify_table(
    agent: Agent[ClassifyDeps, ClassifiedBatch],
    bank_lookup: dict[str, str],
    study_id: str,
    study_name: str,
    table: ParsedTable,
) -> tuple[list[dict], list[str], int, int]:
    """Classify all variables in a table, chunking into batches if needed.

    Args:
        agent: The classification agent.
        bank_lookup: Normalized concept → original bank name for dupe detection.
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table to classify.

    Returns:
        Tuple of (variable dicts, concept names, input_tokens, output_tokens).
    """
    all_vars = table.variables
    n_batches = (len(all_vars) + VARS_PER_BATCH - 1) // VARS_PER_BATCH

    # Build lookup: variable name -> metadata from input data
    meta_by_name = {
        v["name"]: {"description": v.get("description", ""), "id": v.get("id", "")}
        for v in all_vars
    }

    # Split into batches
    batches = [
        all_vars[i : i + VARS_PER_BATCH]
        for i in range(0, len(all_vars), VARS_PER_BATCH)
    ]

    if n_batches == 1:
        # Single batch — no concurrency needed
        batch_result, tok_in, tok_out = await classify_batch(
            agent, bank_lookup, study_id, study_name, table, batches[0]
        )
        batch_results = [(batch_result, tok_in, tok_out)]
    else:
        # Multiple batches — run concurrently with semaphore
        semaphore = asyncio.Semaphore(DEFAULT_CONCURRENCY)
        completed = 0

        async def _run_batch(
            batch_num: int, batch: list[dict[str, str]]
        ) -> tuple[ClassifiedBatch, int, int]:
            nonlocal completed
            async with semaphore:
                result = await classify_batch(
                    agent, bank_lookup, study_id, study_name, table, batch
                )
                completed += 1
                print(
                    f"      batch {completed}/{n_batches} done",
                    file=sys.stderr,
                )
                return result

        batch_results = await asyncio.gather(
            *[_run_batch(i + 1, b) for i, b in enumerate(batches)],
        )

    # Assemble results in original order
    all_concepts_list: list[str] = []
    result_vars: list[dict] = []
    seen: set[str] = set()
    total_in = 0
    total_out = 0

    for batch_result, tok_in, tok_out in batch_results:
        total_in += tok_in
        total_out += tok_out
        for vc in batch_result.variables:
            all_concepts_list.append(vc.concept)
            if vc.variable_name not in seen:
                seen.add(vc.variable_name)
                meta = meta_by_name.get(vc.variable_name, {})
                entry = {"name": vc.variable_name}
                if meta.get("id"):
                    entry["id"] = meta["id"]
                entry["description"] = meta.get("description", "")
                entry["concept"] = vc.concept
                result_vars.append(entry)

    return result_vars, all_concepts_list, total_in, total_out


# ---------------------------------------------------------------------------
# Classify all tables in a study (sequential — bank grows after each table)
# ---------------------------------------------------------------------------


async def classify_study(
    bank: ConceptBank,
    bank_size: int,
    study_id: str,
    tables: list[ParsedTable],
    concurrency: int,
) -> tuple[dict, list[str]]:
    """Classify all tables in a study, growing the bank after each table.

    Tables are processed sequentially so that concepts discovered in earlier
    tables are available in the bank for later tables within the same study.
    A fresh agent is created whenever the bank grows.

    Args:
        bank: Concept bank (mutated — grows during this call).
        bank_size: Max concepts in prompt.
        study_id: The study accession.
        tables: All tables for this study.
        concurrency: Unused (kept for CLI compat); tables are sequential.

    Returns:
        Tuple of (study result dict, list of all concept names assigned).
    """
    study_name = tables[0].study_name if tables else study_id
    # Process largest tables first — they seed the bank with the most concepts
    sorted_tables = sorted(tables, key=lambda t: t.variable_count, reverse=True)

    agent = make_agent(bank, bank_size)
    bank_lookup = _build_bank_lookup(bank)

    table_results = []
    all_concepts: list[str] = []
    total_in = 0
    total_out = 0
    errors = 0

    for t_idx, table in enumerate(sorted_tables, 1):
        print(
            f"    [{t_idx}/{len(sorted_tables)}] {table.table_name} "
            f"({table.variable_count} vars)...",
            file=sys.stderr,
        )
        try:
            variables, concepts, tok_in, tok_out = await classify_table(
                agent, bank_lookup, study_id, study_name, table
            )
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            errors += 1
            print(f"    ERROR on {table.table_name}: {e}", file=sys.stderr)
            continue

        total_in += tok_in
        total_out += tok_out
        all_concepts.extend(concepts)

        table_concepts = sorted({v["concept"] for v in variables})
        table_results.append(
            {
                "tableName": table.table_name,
                "datasetId": table.dataset_id,
                "description": table.description or None,
                "concepts": table_concepts,
                "variables": variables,
            }
        )

        # Grow the bank with concepts from this table; rebuild agent + lookup
        # Exclude "Needs Review" sentinel — it shouldn't be in the bank
        bankable = [c for c in concepts if c != NEEDS_REVIEW_CONCEPT]
        new = bank.register(bankable)
        if new > 0:
            agent = make_agent(bank, bank_size)
            bank_lookup = _build_bank_lookup(bank)

    cost = total_in * 0.80 / 1e6 + total_out * 4 / 1e6
    print(
        f"    tokens: {total_in:,} in / {total_out:,} out (${cost:.3f})"
        + (f"  [{errors} errors]" if errors else ""),
        file=sys.stderr,
    )

    study_result = {
        "studyId": study_id,
        "studyName": study_name,
        "tables": table_results,
    }
    return study_result, all_concepts


# ---------------------------------------------------------------------------
# Write per-study output (same format as v1)
# ---------------------------------------------------------------------------


def write_study_output(study_result: dict, output_dir: Path) -> Path:
    """Write per-study classification to JSON.

    Args:
        study_result: Dict with studyId, studyName, tables.
        output_dir: Directory to write to.

    Returns:
        Path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{study_result['studyId']}.json"
    with open(path, "w") as f:
        json.dump(study_result, f, indent=2)
        f.write("\n")
    return path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    tables_by_study: dict[str, list[ParsedTable]],
    study_ids: list[str],
    bank: ConceptBank,
    bank_size: int,
    concurrency: int,
    dry_run: bool = False,
) -> None:
    """Run the classification pipeline over studies sequentially.

    Args:
        tables_by_study: All tables grouped by study ID.
        study_ids: Ordered list of study IDs to process.
        bank: Concept bank (grows between studies).
        bank_size: Max concepts in prompt.
        concurrency: Max concurrent tables per study.
        dry_run: If True, only print what would run.
    """
    total_studies = len(study_ids)
    total_vars = 0
    total_new_concepts = 0
    start_time = time.time()

    for i, study_id in enumerate(study_ids, 1):
        tables = tables_by_study.get(study_id, [])
        if not tables:
            print(
                f"  [{i}/{total_studies}] {study_id}: no tables, skipping",
                file=sys.stderr,
            )
            continue

        # Check if output already exists (resumability)
        output_path = V2_OUTPUT_DIR / f"{study_id}.json"
        if output_path.exists():
            # Load existing output to register concepts in the bank
            with open(output_path) as f:
                existing = json.load(f)
            concepts = [
                v["concept"]
                for t in existing["tables"]
                for v in t["variables"]
                if v["concept"] != NEEDS_REVIEW_CONCEPT
            ]
            bank.register(concepts)
            print(
                f"  [{i}/{total_studies}] {study_id}: "
                f"already done ({len(concepts)} vars), bank={len(bank.concepts)}",
                file=sys.stderr,
            )
            continue

        n_vars = sum(t.variable_count for t in tables)
        total_vars += n_vars

        if dry_run:
            print(
                f"  [{i}/{total_studies}] {study_id} "
                f"({len(tables)} tables, {n_vars:,} vars) — would classify",
                file=sys.stderr,
            )
            continue

        print(
            f"  [{i}/{total_studies}] {study_id} "
            f"({len(tables)} tables, {n_vars:,} vars)...",
            file=sys.stderr,
        )

        bank_before = len(bank.concepts)

        try:
            study_result, all_concepts = await classify_study(
                bank, bank_size, study_id, tables, concurrency
            )
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    ERROR: {e} — skipping", file=sys.stderr)
            continue

        # Write output
        write_study_output(study_result, V2_OUTPUT_DIR)

        # Bank already grew inside classify_study; count new concepts
        new = len(bank.concepts) - bank_before
        total_new_concepts += new

        n_unique = len({c for c in all_concepts})
        print(
            f"    -> {n_unique} unique concepts, "
            f"{new} new, bank={len(bank.concepts)}",
            file=sys.stderr,
        )

        # Save bank after each study for crash resumability
        bank.save(BANK_PATH)

    elapsed = time.time() - start_time
    print(
        f"\nDone: {total_studies} studies, {total_vars:,} vars, "
        f"{len(bank.concepts)} concepts in bank, "
        f"{total_new_concepts} new this run, "
        f"{elapsed:.0f}s elapsed",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for the v2 variable classification pipeline."""
    parser = argparse.ArgumentParser(
        description="Classify dbGaP variables with a growing concept bank"
    )
    parser.add_argument(
        "--study", help="Classify only this study ID (e.g. phs000007)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Dump each LLM request/response"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without calling the LLM",
    )
    parser.add_argument(
        "--bank-size",
        type=int,
        default=DEFAULT_BANK_SIZE,
        help=f"Top N concepts to include in prompt (default: {DEFAULT_BANK_SIZE})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent tables per study (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--model", help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore existing bank and start from scratch",
    )
    args = parser.parse_args()

    if args.model:
        global MODEL
        MODEL = args.model
        print(f"Model override: {MODEL}", file=sys.stderr)

    if args.debug:
        global DEBUG
        DEBUG = True

    # Load parsed tables
    if not CACHE_FILE.exists():
        print(f"ERROR: Cache file not found: {CACHE_FILE}", file=sys.stderr)
        print("Run: python parse_var_reports.py", file=sys.stderr)
        sys.exit(1)

    print("Loading cached tables...", file=sys.stderr)
    tables = load_cache(CACHE_FILE)
    print(f"Loaded {len(tables)} tables", file=sys.stderr)

    # Group by study
    tables_by_study: dict[str, list[ParsedTable]] = defaultdict(list)
    for t in tables:
        tables_by_study[t.study_id].append(t)

    # Load or create concept bank
    if not args.fresh and BANK_PATH.exists():
        bank = ConceptBank.load(BANK_PATH)
        print(
            f"Loaded concept bank: {len(bank.concepts)} concepts",
            file=sys.stderr,
        )
    else:
        bank = ConceptBank()
        print("Starting with empty concept bank", file=sys.stderr)

    # Determine study order: largest first (by variable count)
    if args.study:
        study_ids = [args.study]
    else:
        study_ids = sorted(
            tables_by_study.keys(),
            key=lambda sid: sum(t.variable_count for t in tables_by_study[sid]),
            reverse=True,
        )

    print(
        f"Processing {len(study_ids)} studies "
        f"(largest first, bank_size={args.bank_size})",
        file=sys.stderr,
    )

    await run_pipeline(
        tables_by_study,
        study_ids,
        bank,
        bank_size=args.bank_size,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
