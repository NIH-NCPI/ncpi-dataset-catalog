"""Classify dbGaP variables against curated concept vocabulary (v4).

Key improvement over v3: packs multiple small tables into single LLM calls
(up to 100 variables per call). Studies with many small tables (4-6 vars each)
go from N API calls down to ceil(total_vars / 100) calls.

Output format: same per-study JSON as v3, written to llm-concepts-v4/.

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python classify_v4.py                       # All studies
    python classify_v4.py --study phs000007     # Single study
    python classify_v4.py --dry-run              # Preview
    python classify_v4.py --concurrency 10       # Concurrent batches
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

# Clear Claude Code sandbox proxy vars — they interfere with httpx/Anthropic API calls
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.anthropic import AnthropicModelSettings

from models import ParsedTable
from parse_var_reports import CACHE_FILE, load_cache

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

VOCAB_PATH = SCRIPT_DIR / "output" / "concept-vocabulary.json"
SEED_PATH = SCRIPT_DIR / "output" / "topmed-seed-concepts.json"
V4_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts-v4"

# ---------------------------------------------------------------------------
# Configuration (overridable via CLI args)
# ---------------------------------------------------------------------------

MODEL = "anthropic:claude-haiku-4-5"
DEBUG = False
VARS_PER_BATCH = 100
MAX_RETRIES = 5
DEFAULT_CONCURRENCY = 10
CONCEPT_NAMESPACE = "topmed"  # prefix added to output concept_ids


# ---------------------------------------------------------------------------
# Output models (Pydantic — structured output from LLM)
# ---------------------------------------------------------------------------


class MatchedVariable(BaseModel):
    """LLM's concept match for a single variable."""

    variable_name: str = Field(description="Exact variable name from input")
    concept_id: str | None = Field(
        description="concept_id from the vocabulary, or null if no match"
    )
    confidence: str = Field(description="high, medium, or low")

    @model_validator(mode="after")
    def check_confidence(self) -> MatchedVariable:
        """Validate confidence is one of the allowed values."""
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError(
                f"confidence must be 'high', 'medium', or 'low', "
                f"got '{self.confidence}'"
            )
        return self


class MatchedTableResult(BaseModel):
    """LLM output for one table's variables within a multi-table batch."""

    table_name: str = Field(description="Exact table name from input")
    variables: list[MatchedVariable] = Field(
        description="One entry per input variable in this table"
    )


class MatchedBatch(BaseModel):
    """LLM output for a batch of tables with their variable matches."""

    tables: list[MatchedTableResult] = Field(
        description="One entry per input table, preserving table order"
    )

    @model_validator(mode="after")
    def check_no_duplicate_variables(self) -> MatchedBatch:
        """Reject duplicate variable names within each table."""
        for table in self.tables:
            seen: set[str] = set()
            dupes: list[str] = []
            for v in table.variables:
                if v.variable_name in seen:
                    dupes.append(v.variable_name)
                seen.add(v.variable_name)
            if dupes:
                raise ValueError(
                    f"Duplicate variable names in table '{table.table_name}': "
                    f"{dupes}. Each variable must appear exactly once per table."
                )
        return self


# ---------------------------------------------------------------------------
# Concept vocabulary
# ---------------------------------------------------------------------------


def load_vocabulary(path: Path) -> list[dict]:
    """Load the concept vocabulary from JSON.

    Args:
        path: Path to concept-vocabulary.json.

    Returns:
        List of concept dicts with concept_id, name, description, etc.
    """
    with open(path) as f:
        return json.load(f)


def format_vocab_for_prompt(vocab: list[dict]) -> str:
    """Format the vocabulary for inclusion in the system prompt.

    Args:
        vocab: List of concept dicts.

    Returns:
        Formatted string listing all concepts with descriptions and examples.
    """
    seen: set[str] = set()
    lines: list[str] = []
    for entry in vocab:
        cid = entry["concept_id"]
        if cid in seen:
            continue
        seen.add(cid)
        desc = entry["description"]
        examples = entry.get("example_variables", [])
        line = f"- {cid}: \"{desc}\""
        if examples:
            ex_str = " | ".join(examples[:3])
            line += f"\n  Examples: {ex_str}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ground truth lookup from TOPMed seed data
# ---------------------------------------------------------------------------


def _phv_number(phv: str) -> str:
    """Extract the phv number without version or consent suffixes.

    Args:
        phv: Full phv accession string.

    Returns:
        Base phv number (e.g. "phv00204712").
    """
    return phv.split(".")[0]


def build_ground_truth_lookup(seed_path: Path) -> dict[str, str]:
    """Build phv_number -> concept_id lookup from TOPMed seed concepts.

    Args:
        seed_path: Path to topmed-seed-concepts.json.

    Returns:
        Dict mapping phv base number to concept_id.
    """
    with open(seed_path) as f:
        data = json.load(f)

    phv_concepts: dict[str, set[str]] = defaultdict(set)
    for concept in data["concepts"]:
        cid = concept["concept_id"]
        for var in concept["component_variables"]:
            phv_num = _phv_number(var["phv"])
            phv_concepts[phv_num].add(cid)

    lookup: dict[str, str] = {}
    for phv_num, concepts in phv_concepts.items():
        if len(concepts) == 1:
            lookup[phv_num] = next(iter(concepts))

    return lookup


# ---------------------------------------------------------------------------
# Deps for output validation
# ---------------------------------------------------------------------------


class MatchDeps:
    """Dependencies passed to the agent for output validation."""

    def __init__(
        self,
        input_tables: dict[str, set[str]],
        valid_concept_ids: set[str],
    ):
        """Initialize match dependencies.

        Args:
            input_tables: table_name -> set of expected variable names.
            valid_concept_ids: Set of valid concept_ids from vocabulary.
        """
        self.input_tables = input_tables
        self.valid_concept_ids = valid_concept_ids


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt(vocab: list[dict]) -> str:
    """Build the system prompt with the fixed concept vocabulary.

    Args:
        vocab: The concept vocabulary list.

    Returns:
        Complete system prompt string.
    """
    vocab_section = format_vocab_for_prompt(vocab)
    n_concepts = len({v["concept_id"] for v in vocab})

    return f"""You are a biomedical variable classifier. You match dbGaP study
variables to a fixed vocabulary of {n_concepts} expert-curated concepts.

## Rules

1. For each variable, determine if it measures something captured by one of
   the concepts below. Consider the variable name, description, AND the
   table context (name + description).

2. Return the concept_id if there's a match, or null if the variable doesn't
   fit any concept. It is EXPECTED that many variables will be null — only
   match when you are confident.

3. Use the table name and description as context — they tell you what instrument
   or procedure produced the data. But do NOT let the table name override what
   the variable itself measures.

4. When assigning confidence:
   - "high": The variable clearly and directly measures what the concept describes
   - "medium": The variable likely matches but there's some ambiguity
   - "low": The match is plausible but uncertain

5. DO NOT invent concept_ids. Only use IDs from the vocabulary below, or null.

6. Match based on what value the variable contains, not what it references.
   "Age at BMI measurement" contains an age, not a BMI — it should get null
   (unless there is an age concept it matches).

7. The input may contain ONE or MULTIPLE tables. Return results grouped by
   table_name, preserving the exact table names from the input.

## Concept Vocabulary ({n_concepts} concepts)

Match each variable to ONE of these concepts, or null if none match.

{vocab_section}
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def make_agent(vocab: list[dict]) -> Agent[MatchDeps, MatchedBatch]:
    """Create the matching agent with the concept vocabulary.

    Args:
        vocab: The concept vocabulary list.

    Returns:
        Configured pydantic-ai Agent.
    """
    settings: AnthropicModelSettings = {
        "anthropic_cache_instructions": True,
        "max_tokens": 16384,
        "temperature": 0.0,
    }
    agent: Agent[MatchDeps, MatchedBatch] = Agent(
        MODEL,
        deps_type=MatchDeps,
        output_type=MatchedBatch,
        system_prompt=build_system_prompt(vocab),
        retries=3,
        model_settings=settings,
    )

    @agent.output_validator
    async def validate_completeness(
        ctx: RunContext[MatchDeps], result: MatchedBatch
    ) -> MatchedBatch:
        """Ensure every input table and variable is present and concept_ids are valid.

        Args:
            ctx: Run context with input tables and valid concept_ids.
            result: LLM output to validate.

        Returns:
            Validated result.
        """
        output_tables = {t.table_name: t for t in result.tables}

        # Check all expected tables are present
        missing_tables = set(ctx.deps.input_tables.keys()) - set(output_tables.keys())
        if missing_tables:
            msg = f"Missing tables: {sorted(missing_tables)}"
            print(f"    RETRY: {msg}", file=sys.stderr)
            raise ModelRetry(msg)

        # Check variables within each table
        for table_name, expected_vars in ctx.deps.input_tables.items():
            if table_name not in output_tables:
                continue
            output_vars = {v.variable_name for v in output_tables[table_name].variables}
            missing = expected_vars - output_vars
            if missing:
                msg = (
                    f"Missing {len(missing)} variables in table "
                    f"'{table_name}': {sorted(missing)[:5]}"
                )
                print(f"    RETRY: {msg}", file=sys.stderr)
                raise ModelRetry(msg)
            extra = output_vars - expected_vars
            if extra:
                msg = (
                    f"Extra variables in table '{table_name}' "
                    f"not in input: {sorted(extra)[:5]}"
                )
                print(f"    RETRY: {msg}", file=sys.stderr)
                raise ModelRetry(msg)

        # Validate concept_ids against vocabulary
        for table_result in result.tables:
            for v in table_result.variables:
                if v.concept_id is not None and v.concept_id not in ctx.deps.valid_concept_ids:
                    msg = (
                        f"Invalid concept_id '{v.concept_id}' for variable "
                        f"'{v.variable_name}' in table '{table_result.table_name}'. "
                        f"Must be one of the vocabulary concept_ids or null."
                    )
                    print(f"    RETRY: {msg}", file=sys.stderr)
                    raise ModelRetry(msg)

        return result

    return agent


# ---------------------------------------------------------------------------
# User message formatting (multi-table)
# ---------------------------------------------------------------------------

# A batch item: one table with a subset of its variables
BatchItem = tuple[ParsedTable, list[dict[str, str]]]


def format_batch_prompt(
    study_id: str,
    study_name: str,
    items: list[BatchItem],
) -> str:
    """Format multiple tables and their variables into the user message.

    Args:
        study_id: The study accession (e.g. phs000007).
        study_name: Human-readable study name.
        items: List of (table, variables) pairs to include.

    Returns:
        Formatted string with all tables and their variables.
    """
    parts = [f"Study: {study_id} — {study_name}\n"]

    for table, variables in items:
        desc = table.description if table.description else "(none)"
        var_lines = []
        for v in variables:
            name = v["name"]
            d = v.get("description")
            var_lines.append(f"  {name}: {d}" if d else f"  {name}")
        vars_block = "\n".join(var_lines)

        parts.append(
            f"TABLE: {table.table_name}  ({len(variables):,} vars)\n"
            f"DESCRIPTION: {desc}\n"
            f"VARIABLES:\n{vars_block}"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Classify a batch of table items (with retry)
# ---------------------------------------------------------------------------


async def classify_batch(
    agent: Agent[MatchDeps, MatchedBatch],
    valid_concept_ids: set[str],
    study_id: str,
    study_name: str,
    items: list[BatchItem],
) -> tuple[MatchedBatch, int, int]:
    """Run the agent on a batch of table items with retry on rate-limit errors.

    Args:
        agent: The matching agent.
        valid_concept_ids: Set of valid concept_ids.
        study_id: The study accession.
        study_name: Human-readable study name.
        items: List of (table, variables) pairs to classify.

    Returns:
        Tuple of (MatchedBatch, input_tokens, output_tokens).
    """
    prompt = format_batch_prompt(study_id, study_name, items)
    input_tables = {
        table.table_name: {v["name"] for v in variables}
        for table, variables in items
    }
    deps = MatchDeps(
        input_tables=input_tables,
        valid_concept_ids=valid_concept_ids,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await agent.run(prompt, deps=deps)
            usage = result.usage()
            if DEBUG:
                matches_str = "\n".join(
                    f"    [{tr.table_name}] {mv.variable_name}: "
                    f"{mv.concept_id} ({mv.confidence})"
                    for tr in result.output.tables
                    for mv in tr.variables
                )
                total_vars = sum(len(v) for _, v in items)
                print(
                    f"\n{'─'*60}\n"
                    f"REQUEST  [{len(items)} tables, {total_vars} vars]\n{prompt}\n"
                    f"{'─'*60}\n"
                    f"RESPONSE\n"
                    f"{matches_str}\n"
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

    raise RuntimeError("classify_batch: all retries exhausted")


# ---------------------------------------------------------------------------
# Batch packing — group small tables into multi-table batches
# ---------------------------------------------------------------------------


def pack_batches(items: list[BatchItem]) -> list[list[BatchItem]]:
    """Pack batch items into multi-table batches of <= VARS_PER_BATCH variables.

    Uses first-fit decreasing: sorts items largest-first, then packs each
    into the first batch that has room.

    Args:
        items: List of (table, variables) pairs, each with <= VARS_PER_BATCH vars.

    Returns:
        List of multi-table batches, each a list of (table, variables) pairs.
    """
    if not items:
        return []

    # Sort largest first for better packing
    sorted_items = sorted(items, key=lambda x: len(x[1]), reverse=True)

    batches: list[list[BatchItem]] = []
    batch_sizes: list[int] = []

    for item in sorted_items:
        item_size = len(item[1])
        # Try to fit into an existing batch
        placed = False
        for i, batch in enumerate(batches):
            if batch_sizes[i] + item_size <= VARS_PER_BATCH:
                batch.append(item)
                batch_sizes[i] += item_size
                placed = True
                break
        if not placed:
            batches.append([item])
            batch_sizes.append(item_size)

    return batches


# ---------------------------------------------------------------------------
# Classify all tables in a study
# ---------------------------------------------------------------------------


async def classify_study(
    agent: Agent[MatchDeps, MatchedBatch],
    valid_concept_ids: set[str],
    study_id: str,
    tables: list[ParsedTable],
    ground_truth: dict[str, str],
    semaphore: asyncio.Semaphore,
    on_batch_done: Callable[[], None] | None = None,
) -> dict:
    """Classify all tables in a study using multi-table batching.

    Args:
        agent: The matching agent.
        valid_concept_ids: Set of valid concept_ids.
        study_id: The study accession.
        tables: All tables for this study.
        ground_truth: phv -> concept_id lookup.
        semaphore: Shared semaphore for concurrency control across studies.
        on_batch_done: Optional callback after each batch completes.

    Returns:
        Study result dict.
    """
    study_name = tables[0].study_name if tables else study_id

    # 1. Separate ground truth vs LLM vars per table, build metadata lookup
    gt_by_table: dict[str, list[dict]] = {}
    meta_lookup: dict[tuple[str, str], dict] = {}  # (table_name, var_name) -> meta
    batch_items: list[BatchItem] = []

    for table in tables:
        gt_vars: list[dict] = []
        llm_vars: list[dict[str, str]] = []

        for v in table.variables:
            phv = v.get("id", "")
            phv_num = _phv_number(phv)
            if phv_num in ground_truth:
                gt_vars.append({
                    "name": v["name"],
                    "id": v.get("id", ""),
                    "description": v.get("description", ""),
                    "concept_id": f"{CONCEPT_NAMESPACE}:{ground_truth[phv_num]}",
                    "confidence": "high",
                    "source": "ground_truth",
                })
            else:
                llm_vars.append(v)
                meta_lookup[(table.table_name, v["name"])] = {
                    "description": v.get("description", ""),
                    "id": v.get("id", ""),
                }

        gt_by_table[table.table_name] = gt_vars

        # Chunk LLM vars into <= VARS_PER_BATCH pieces
        if llm_vars:
            for i in range(0, len(llm_vars), VARS_PER_BATCH):
                chunk = llm_vars[i:i + VARS_PER_BATCH]
                batch_items.append((table, chunk))

    # 2. Pack small batch items into multi-table batches
    batches = pack_batches(batch_items)

    total_batches = len(batches)
    batches_done = 0

    # 3. Run batches concurrently
    async def _run_batch(
        batch: list[BatchItem],
    ) -> tuple[MatchedBatch, int, int]:
        nonlocal batches_done
        async with semaphore:
            result = await classify_batch(
                agent, valid_concept_ids, study_id, study_name, batch,
            )
            batches_done += 1
            if on_batch_done:
                on_batch_done()
            n_tables = len(batch)
            n_vars = sum(len(v) for _, v in batch)
            print(
                f"    batch {batches_done}/{total_batches} "
                f"({n_tables} tables, {n_vars} vars)",
                file=sys.stderr,
            )
            return result

    if not batches:
        batch_results: list[tuple[MatchedBatch, int, int]] = []
    else:
        batch_results = await asyncio.gather(
            *[_run_batch(b) for b in batches],
        )

    # 4. Demux LLM results back to per-table
    llm_by_table: dict[str, list[dict]] = defaultdict(list)
    total_in = 0
    total_out = 0

    for batch_result, tok_in, tok_out in batch_results:
        total_in += tok_in
        total_out += tok_out
        for table_result in batch_result.tables:
            for mv in table_result.variables:
                meta = meta_lookup.get(
                    (table_result.table_name, mv.variable_name), {}
                )
                namespaced_cid = (
                    f"{CONCEPT_NAMESPACE}:{mv.concept_id}"
                    if mv.concept_id is not None
                    else None
                )
                llm_by_table[table_result.table_name].append({
                    "name": mv.variable_name,
                    "id": meta.get("id", ""),
                    "description": meta.get("description", ""),
                    "concept_id": namespaced_cid,
                    "confidence": mv.confidence,
                    "source": "llm",
                })

    # 5. Assemble per-table results (GT + LLM)
    table_lookup = {t.table_name: t for t in tables}
    table_results = []
    total_gt = 0
    total_llm = 0

    for table in sorted(tables, key=lambda t: t.variable_count, reverse=True):
        gt_vars_list = gt_by_table.get(table.table_name, [])
        llm_vars_list = llm_by_table.get(table.table_name, [])
        all_vars = gt_vars_list + llm_vars_list
        total_gt += len(gt_vars_list)
        total_llm += len(llm_vars_list)

        table_results.append({
            "tableName": table.table_name,
            "datasetId": table.dataset_id,
            "description": table.description or None,
            "variables": all_vars,
        })

    cost = total_in * 0.80 / 1e6 + total_out * 4 / 1e6
    print(
        f"    tokens: {total_in:,} in / {total_out:,} out (${cost:.3f})"
        f"  [gt={total_gt}, llm={total_llm}]",
        file=sys.stderr,
    )

    return {
        "studyId": study_id,
        "studyName": study_name,
        "tables": table_results,
    }


# ---------------------------------------------------------------------------
# Write per-study output
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
    vocab: list[dict],
    ground_truth: dict[str, str],
    concurrency: int,
    dry_run: bool = False,
) -> None:
    """Run the v4 classification pipeline over studies in parallel.

    Studies run concurrently, sharing a single semaphore that limits
    total in-flight LLM calls across all studies.

    Args:
        tables_by_study: All tables grouped by study ID.
        study_ids: Ordered list of study IDs to process.
        vocab: Concept vocabulary.
        ground_truth: phv -> concept_id lookup.
        concurrency: Max concurrent LLM calls across all studies.
        dry_run: If True, only print what would run.
    """
    valid_concept_ids = {v["concept_id"] for v in vocab}
    agent = make_agent(vocab)
    total_studies = len(study_ids)
    start_time = time.time()

    # Shared semaphore controls total concurrent LLM calls across all studies
    semaphore = asyncio.Semaphore(concurrency)
    studies_done = 0
    studies_total_vars = 0

    if dry_run:
        for i, study_id in enumerate(study_ids, 1):
            tables = tables_by_study.get(study_id, [])
            if not tables:
                continue
            output_path = V4_OUTPUT_DIR / f"{study_id}.json"
            if output_path.exists():
                continue
            n_vars = sum(t.variable_count for t in tables)
            gt_count = sum(
                1 for t in tables for v in t.variables
                if _phv_number(v.get("id", "")) in ground_truth
            )
            llm_items: list[BatchItem] = []
            for t in tables:
                llm_vars = [
                    v for v in t.variables
                    if _phv_number(v.get("id", "")) not in ground_truth
                ]
                if llm_vars:
                    for j in range(0, len(llm_vars), VARS_PER_BATCH):
                        llm_items.append((t, llm_vars[j:j + VARS_PER_BATCH]))
            packed = pack_batches(llm_items)
            print(
                f"  [{i}/{total_studies}] {study_id} "
                f"({len(tables)} tables, {n_vars:,} vars, "
                f"{gt_count} ground truth, {len(packed)} LLM batches) "
                f"— would classify",
                file=sys.stderr,
            )
        return

    async def _run_study(study_id: str) -> None:
        nonlocal studies_done, studies_total_vars

        tables = tables_by_study.get(study_id, [])
        if not tables:
            return

        # Check if output already exists (resumability)
        output_path = V4_OUTPUT_DIR / f"{study_id}.json"
        if output_path.exists():
            return

        n_vars = sum(t.variable_count for t in tables)
        studies_total_vars += n_vars

        print(
            f"  {study_id} "
            f"({len(tables)} tables, {n_vars:,} vars)...",
            file=sys.stderr,
        )

        try:
            study_result = await classify_study(
                agent, valid_concept_ids, study_id, tables,
                ground_truth, semaphore,
            )
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    {study_id} ERROR: {e} — skipping", file=sys.stderr)
            return

        write_study_output(study_result, V4_OUTPUT_DIR)

        studies_done += 1

        # Summary stats
        matched = sum(
            1 for t in study_result["tables"]
            for v in t["variables"]
            if v.get("concept_id") is not None
        )
        total = sum(len(t["variables"]) for t in study_result["tables"])
        elapsed = time.time() - start_time
        rate = f"{studies_done / elapsed:.1f} studies/s" if elapsed > 0 else ""
        if total > 0:
            print(
                f"    {study_id} -> {matched}/{total} matched "
                f"({matched/total*100:.1f}%)  "
                f"[{studies_done} done, {rate}]",
                file=sys.stderr,
            )

    await asyncio.gather(*[_run_study(sid) for sid in study_ids])

    elapsed = time.time() - start_time
    print(
        f"\nDone: {studies_done} studies, {studies_total_vars:,} vars, "
        f"{elapsed:.0f}s elapsed",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for the v4 concept matching pipeline."""
    parser = argparse.ArgumentParser(
        description="Classify dbGaP variables against concept vocabulary (v4, multi-table batching)"
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
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent batches (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--model", help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)"
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

    # Load concept vocabulary
    if not VOCAB_PATH.exists():
        print(f"ERROR: Vocabulary not found: {VOCAB_PATH}", file=sys.stderr)
        sys.exit(1)
    vocab = load_vocabulary(VOCAB_PATH)
    n_concepts = len({v["concept_id"] for v in vocab})
    print(f"Loaded {n_concepts} concepts from vocabulary", file=sys.stderr)

    # Build ground truth lookup from seed data
    if SEED_PATH.exists():
        ground_truth = build_ground_truth_lookup(SEED_PATH)
        print(
            f"Built ground truth lookup: {len(ground_truth)} phv mappings",
            file=sys.stderr,
        )
    else:
        ground_truth = {}
        print("No seed data found, skipping ground truth", file=sys.stderr)

    # Group by study
    tables_by_study: dict[str, list[ParsedTable]] = defaultdict(list)
    for t in tables:
        tables_by_study[t.study_id].append(t)

    # Determine study order: smallest first (quick results for review)
    if args.study:
        study_ids = [args.study]
    else:
        study_ids = sorted(
            tables_by_study.keys(),
            key=lambda sid: sum(t.variable_count for t in tables_by_study[sid]),
        )

    print(
        f"Processing {len(study_ids)} studies (smallest first)",
        file=sys.stderr,
    )

    await run_pipeline(
        tables_by_study,
        study_ids,
        vocab,
        ground_truth,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
