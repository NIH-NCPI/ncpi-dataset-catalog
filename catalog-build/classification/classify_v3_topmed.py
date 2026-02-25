"""Classify dbGaP variables against 78 expert-curated TOPMed concepts.

Unlike the v2 classifier (classify_with_memory.py) which uses open-ended
concept naming with a growing bank, v3 constrains the LLM to a fixed
vocabulary of 78 TOPMed concepts. Each variable either matches one concept
or gets null (no match).

Pre-classification: component variables from topmed-seed-concepts.json that
map to exactly one concept are auto-classified without an LLM call.

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python classify_v3_topmed.py                      # All studies
    python classify_v3_topmed.py --study phs000007    # Single study
    python classify_v3_topmed.py --dry-run             # Preview
    python classify_v3_topmed.py --concurrency 10      # Concurrent batches
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Callable
import sys
import time
from collections import defaultdict
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
V3_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts-v3"

# ---------------------------------------------------------------------------
# Configuration (overridable via CLI args)
# ---------------------------------------------------------------------------

MODEL = "anthropic:claude-haiku-4-5"
DEBUG = False
VARS_PER_BATCH = 100
MAX_RETRIES = 5
DEFAULT_CONCURRENCY = 10


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


class MatchedBatch(BaseModel):
    """LLM output for a batch of variable matches."""

    variables: list[MatchedVariable] = Field(
        description="One entry per input variable"
    )

    @model_validator(mode="after")
    def check_no_duplicate_variables(self) -> MatchedBatch:
        """Reject duplicate variable names in the output."""
        seen: set[str] = set()
        dupes: list[str] = []
        for v in self.variables:
            if v.variable_name in seen:
                dupes.append(v.variable_name)
            seen.add(v.variable_name)
        if dupes:
            raise ValueError(
                f"Duplicate variable names in output: {dupes}. "
                f"Each variable must appear exactly once."
            )
        return self


# ---------------------------------------------------------------------------
# Concept vocabulary
# ---------------------------------------------------------------------------


def load_vocabulary(path: Path) -> list[dict]:
    """Load the 78-concept vocabulary from JSON.

    Args:
        path: Path to concept-vocabulary.json.

    Returns:
        List of concept dicts with concept_id, name, description, etc.
    """
    with open(path) as f:
        return json.load(f)


def build_vocab_lookup(vocab: list[dict]) -> dict[str, dict]:
    """Build concept_id → vocab entry lookup (deduplicating).

    Args:
        vocab: List of concept dicts.

    Returns:
        Dict mapping concept_id to the first matching vocab entry.
    """
    lookup: dict[str, dict] = {}
    for entry in vocab:
        cid = entry["concept_id"]
        if cid not in lookup:
            lookup[cid] = entry
    return lookup


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

    "phv00204712.v1" -> "phv00204712"
    "phv00098580.v6.p3" -> "phv00098580"

    Args:
        phv: Full phv accession string.

    Returns:
        Base phv number (e.g. "phv00204712").
    """
    return phv.split(".")[0]


def build_ground_truth_lookup(seed_path: Path) -> dict[str, str]:
    """Build phv_number → concept_id lookup from TOPMed seed concepts.

    The seed file contains only measurement variables (covariates are
    stripped during extraction). This function just maps each phv to its
    concept, excluding phvs that appear under multiple concepts (ambiguous).

    Args:
        seed_path: Path to topmed-seed-concepts.json.

    Returns:
        Dict mapping phv base number to concept_id.
    """
    with open(seed_path) as f:
        data = json.load(f)

    # Collect phv_number → concept_id mappings
    phv_concepts: dict[str, set[str]] = defaultdict(set)
    for concept in data["concepts"]:
        cid = concept["concept_id"]
        for var in concept["component_variables"]:
            phv_num = _phv_number(var["phv"])
            phv_concepts[phv_num].add(cid)

    # Only keep phvs with exactly one concept (shared phvs are ambiguous)
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
        input_variable_names: set[str],
        valid_concept_ids: set[str],
    ):
        """Initialize match dependencies.

        Args:
            input_variable_names: Expected variable names in output.
            valid_concept_ids: Set of valid concept_ids from vocabulary.
        """
        self.input_variable_names = input_variable_names
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
    valid_ids = {v["concept_id"] for v in vocab}

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
        """Ensure every input variable is present and concept_ids are valid.

        Args:
            ctx: Run context with input variable names and valid concept_ids.
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

        # Validate concept_ids against vocabulary
        for v in result.variables:
            if v.concept_id is not None and v.concept_id not in valid_ids:
                msg = (
                    f"Invalid concept_id '{v.concept_id}' for variable "
                    f"'{v.variable_name}'. Must be one of the vocabulary "
                    f"concept_ids or null."
                )
                print(f"    RETRY: {msg}", file=sys.stderr)
                raise ModelRetry(msg)

        return result

    return agent


# ---------------------------------------------------------------------------
# User message formatting
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
    agent: Agent[MatchDeps, MatchedBatch],
    valid_concept_ids: set[str],
    study_id: str,
    study_name: str,
    table: ParsedTable,
    variables: list[dict[str, str]],
) -> tuple[MatchedBatch, int, int]:
    """Run the agent on a batch of variables with retry on rate-limit errors.

    Args:
        agent: The matching agent.
        valid_concept_ids: Set of valid concept_ids.
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table (for context).
        variables: The variable subset to classify.

    Returns:
        Tuple of (MatchedBatch, input_tokens, output_tokens).
    """
    prompt = format_table_prompt(study_id, study_name, table, variables)
    input_names = {v["name"] for v in variables}
    deps = MatchDeps(
        input_variable_names=input_names,
        valid_concept_ids=valid_concept_ids,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await agent.run(prompt, deps=deps)
            usage = result.usage()
            if DEBUG:
                matches_str = "\n".join(
                    f"    {mv.variable_name}: {mv.concept_id} ({mv.confidence})"
                    for mv in result.output.variables
                )
                print(
                    f"\n{'─'*60}\n"
                    f"REQUEST  [{table.table_name}] ({len(variables)} vars)\n{prompt}\n"
                    f"{'─'*60}\n"
                    f"RESPONSE [{table.table_name}]\n"
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
    # All retries exhausted without a rate-limit error raising —
    # this is unreachable since the loop always returns or raises,
    # but satisfies the type checker.
    raise RuntimeError("classify_batch: all retries exhausted")


# ---------------------------------------------------------------------------
# Classify all variables in a table (chunking into batches)
# ---------------------------------------------------------------------------


async def classify_table(
    agent: Agent[MatchDeps, MatchedBatch],
    valid_concept_ids: set[str],
    study_id: str,
    study_name: str,
    table: ParsedTable,
    ground_truth: dict[str, str],
    semaphore: asyncio.Semaphore,
    on_batch_done: Callable[[], None] | None = None,
) -> tuple[list[dict], int, int, int, int]:
    """Classify all variables in a table, pre-classifying ground truth first.

    Args:
        agent: The matching agent.
        valid_concept_ids: Set of valid concept_ids.
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table to classify.
        ground_truth: phv → concept_id lookup for pre-classification.
        semaphore: Shared semaphore for concurrency control.
        on_batch_done: Optional callback invoked after each batch completes.

    Returns:
        Tuple of (variable dicts, input_tokens, output_tokens,
                  ground_truth_count, llm_count).
    """
    all_vars = table.variables

    # Separate ground truth vs LLM-needed variables
    gt_vars: list[dict] = []
    llm_vars: list[dict[str, str]] = []

    for v in all_vars:
        phv = v.get("id", "")
        phv_num = _phv_number(phv)
        if phv_num in ground_truth:
            gt_vars.append({
                "name": v["name"],
                "id": v.get("id", ""),
                "description": v.get("description", ""),
                "concept_id": ground_truth[phv_num],
                "confidence": "high",
                "source": "ground_truth",
            })
        else:
            llm_vars.append(v)

    # If no LLM vars needed, return just ground truth
    if not llm_vars:
        return gt_vars, 0, 0, len(gt_vars), 0

    # Build lookup: variable name -> metadata from input data
    meta_by_name = {
        v["name"]: {"description": v.get("description", ""), "id": v.get("id", "")}
        for v in llm_vars
    }

    # Split LLM vars into batches
    batches = [
        llm_vars[i : i + VARS_PER_BATCH]
        for i in range(0, len(llm_vars), VARS_PER_BATCH)
    ]

    async def _run_batch(
        batch: list[dict[str, str]],
    ) -> tuple[MatchedBatch, int, int]:
        async with semaphore:
            result = await classify_batch(
                agent, valid_concept_ids, study_id, study_name, table, batch
            )
            if on_batch_done:
                on_batch_done()
            return result

    batch_results = await asyncio.gather(
        *[_run_batch(b) for b in batches],
    )

    # Assemble LLM results
    llm_result_vars: list[dict] = []
    seen: set[str] = set()
    total_in = 0
    total_out = 0

    for batch_result, tok_in, tok_out in batch_results:
        total_in += tok_in
        total_out += tok_out
        for mv in batch_result.variables:
            if mv.variable_name not in seen:
                seen.add(mv.variable_name)
                meta = meta_by_name.get(mv.variable_name, {})
                entry = {
                    "name": mv.variable_name,
                    "id": meta.get("id", ""),
                    "description": meta.get("description", ""),
                    "concept_id": mv.concept_id,
                    "confidence": mv.confidence,
                    "source": "llm",
                }
                llm_result_vars.append(entry)

    # Combine: ground truth first, then LLM results
    all_result_vars = gt_vars + llm_result_vars
    return all_result_vars, total_in, total_out, len(gt_vars), len(llm_result_vars)


# ---------------------------------------------------------------------------
# Classify all tables in a study
# ---------------------------------------------------------------------------


async def classify_study(
    agent: Agent[MatchDeps, MatchedBatch],
    valid_concept_ids: set[str],
    study_id: str,
    tables: list[ParsedTable],
    ground_truth: dict[str, str],
    concurrency: int,
) -> dict:
    """Classify all tables in a study, running tables concurrently.

    Args:
        agent: The matching agent.
        valid_concept_ids: Set of valid concept_ids.
        study_id: The study accession.
        tables: All tables for this study.
        ground_truth: phv → concept_id lookup.
        concurrency: Max concurrent batches.

    Returns:
        Study result dict.
    """
    study_name = tables[0].study_name if tables else study_id
    sorted_tables = sorted(tables, key=lambda t: t.variable_count, reverse=True)
    semaphore = asyncio.Semaphore(concurrency)
    tables_done = 0
    batches_done = 0
    total_batches = 0
    for t in sorted_tables:
        llm_var_count = sum(
            1 for v in t.variables
            if _phv_number(v.get("id", "")) not in ground_truth
        )
        if llm_var_count > 0:
            total_batches += -(-llm_var_count // VARS_PER_BATCH)

    def _on_batch_done() -> None:
        nonlocal batches_done
        batches_done += 1
        print(
            f"    batch {batches_done}/{total_batches}",
            file=sys.stderr,
        )

    async def _run_table(
        table: ParsedTable,
    ) -> dict | None:
        nonlocal tables_done
        try:
            variables, tok_in, tok_out, gt_count, llm_count = await classify_table(
                agent, valid_concept_ids, study_id, study_name,
                table, ground_truth, semaphore, _on_batch_done,
            )
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    ERROR on {table.table_name}: {e}", file=sys.stderr)
            return None

        tables_done += 1
        print(
            f"    [{tables_done}/{len(sorted_tables)}] {table.table_name} "
            f"({table.variable_count} vars) done",
            file=sys.stderr,
        )
        return {
            "tableName": table.table_name,
            "datasetId": table.dataset_id,
            "description": table.description or None,
            "variables": variables,
            "_tok_in": tok_in,
            "_tok_out": tok_out,
            "_gt_count": gt_count,
            "_llm_count": llm_count,
        }

    results = await asyncio.gather(
        *[_run_table(t) for t in sorted_tables],
    )

    # Collect results, stripping internal fields
    table_results = []
    total_in = 0
    total_out = 0
    total_gt = 0
    total_llm = 0
    errors = 0

    for r in results:
        if r is None:
            errors += 1
            continue
        total_in += r.pop("_tok_in")
        total_out += r.pop("_tok_out")
        total_gt += r.pop("_gt_count")
        total_llm += r.pop("_llm_count")
        table_results.append(r)

    cost = total_in * 0.80 / 1e6 + total_out * 4 / 1e6
    print(
        f"    tokens: {total_in:,} in / {total_out:,} out (${cost:.3f})"
        f"  [gt={total_gt}, llm={total_llm}]"
        + (f"  [{errors} errors]" if errors else ""),
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
    """Run the v3 classification pipeline over studies.

    Args:
        tables_by_study: All tables grouped by study ID.
        study_ids: Ordered list of study IDs to process.
        vocab: Concept vocabulary.
        ground_truth: phv → concept_id lookup.
        concurrency: Max concurrent batches per table.
        dry_run: If True, only print what would run.
    """
    valid_concept_ids = {v["concept_id"] for v in vocab}
    agent = make_agent(vocab)
    total_studies = len(study_ids)
    total_vars = 0
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
        output_path = V3_OUTPUT_DIR / f"{study_id}.json"
        if output_path.exists():
            print(
                f"  [{i}/{total_studies}] {study_id}: already done, skipping",
                file=sys.stderr,
            )
            continue

        n_vars = sum(t.variable_count for t in tables)
        total_vars += n_vars

        if dry_run:
            # Count ground truth vars for this study
            gt_count = 0
            for t in tables:
                for v in t.variables:
                    phv = v.get("id", "")
                    if _phv_number(phv) in ground_truth:
                        gt_count += 1
            print(
                f"  [{i}/{total_studies}] {study_id} "
                f"({len(tables)} tables, {n_vars:,} vars, "
                f"{gt_count} ground truth) — would classify",
                file=sys.stderr,
            )
            continue

        print(
            f"  [{i}/{total_studies}] {study_id} "
            f"({len(tables)} tables, {n_vars:,} vars)...",
            file=sys.stderr,
        )

        try:
            study_result = await classify_study(
                agent, valid_concept_ids, study_id, tables,
                ground_truth, concurrency,
            )
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    ERROR: {e} — skipping", file=sys.stderr)
            continue

        write_study_output(study_result, V3_OUTPUT_DIR)

        # Summary stats
        matched = sum(
            1 for t in study_result["tables"]
            for v in t["variables"]
            if v.get("concept_id") is not None
        )
        total = sum(len(t["variables"]) for t in study_result["tables"])
        print(
            f"    -> {matched}/{total} matched "
            f"({matched/total*100:.1f}%)" if total > 0 else "    -> 0 vars",
            file=sys.stderr,
        )

    elapsed = time.time() - start_time
    print(
        f"\nDone: {total_studies} studies, {total_vars:,} vars, "
        f"{elapsed:.0f}s elapsed",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for the v3 TOPMed concept matching pipeline."""
    parser = argparse.ArgumentParser(
        description="Classify dbGaP variables against TOPMed concept vocabulary"
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
