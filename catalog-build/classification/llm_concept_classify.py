"""LLM-based variable-level concept classification for dbGaP tables.

Assigns a standardized medical concept name to every variable in every table,
enabling browsing by measurement type. Tables and studies inherit the union
of their variables' concepts.

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python llm_concept_classify.py --study phs000280                    # One study
    python llm_concept_classify.py --study phs000280 --table UBMDBF02  # One table (debug)
    python llm_concept_classify.py --all                                # All studies
    python llm_concept_classify.py                                      # Only studies without existing output
    python llm_concept_classify.py --model anthropic:claude-sonnet-4-5-20250929 --study phs000280
    python llm_concept_classify.py --debug --study phs000280
    python llm_concept_classify.py --summary                            # Regenerate concept-summary.json
    python llm_concept_classify.py --normalize                          # Merge synonym concepts via LLM

Observability:
    pip install "pydantic-ai-slim[logfire]"
    logfire auth
    python llm_concept_classify.py --logfire --study phs000280
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Clear Claude Code sandbox proxy vars — they interfere with httpx/Anthropic API calls
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from models import ParsedTable
from parse_var_reports import CACHE_FILE, load_cache

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

CONCEPT_PROMPT_PATH = SCRIPT_DIR / "CONCEPT_PROMPT.md"
CONCEPT_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-concepts"
SUMMARY_PATH = SCRIPT_DIR / "output" / "concept-summary.json"
NORMALIZATION_MAP_PATH = SCRIPT_DIR / "output" / "concept-normalization-map.json"

# Set via --debug flag; when True, dump each request/response to stderr
DEBUG = False

# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------


class LLMVariableConcept(BaseModel):
    """LLM's concept assignment for a single variable."""

    variable_name: str = Field(description="Exact variable name from input")
    concept: str = Field(description="Standardized medical concept in Title Case")


class LLMTableConcepts(BaseModel):
    """LLM's concept assignments for all variables in a table (or batch)."""

    variables: list[LLMVariableConcept]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    """Read CONCEPT_PROMPT.md and append task-specific instructions."""
    prompt_md = CONCEPT_PROMPT_PATH.read_text()
    instructions = """
## Your Task

You will receive a table from a dbGaP study with its name, description, and
a list of variables (name + description). Assign a concept to EVERY variable.

**Instructions:**

1. Return one entry per variable, using the exact variable name from the input.
2. Use the table name and description as context — they tell you what instrument
   or procedure produced the data, which helps disambiguate opaque variable names.
3. Apply the naming rules and granularity examples above consistently.
4. When multiple variables clearly measure the same thing (e.g. SBP reading 1,
   SBP reading 2), they must get the same concept name.
5. Prefer reusing concept names you have already assigned in this batch over
   inventing slight variations.
"""
    return prompt_md + "\n" + instructions


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_agent: Agent[None, LLMTableConcepts] | None = None

MODEL = "anthropic:claude-haiku-4-5"


def get_agent() -> Agent[None, LLMTableConcepts]:
    """Return the shared Agent instance, creating it on first call."""
    global _agent
    if _agent is None:
        _agent = Agent(
            MODEL,
            output_type=LLMTableConcepts,
            system_prompt=build_system_prompt(),
            retries=3,
            model_settings={
                "anthropic_cache_instructions": True,
                "max_tokens": 16384,
            },
        )
    return _agent


# ---------------------------------------------------------------------------
# Building the user message for a single table (or batch)
# ---------------------------------------------------------------------------

VARS_PER_BATCH = 100


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
# Running the agent on a single table (with batching)
# ---------------------------------------------------------------------------

MAX_RETRIES = 5


async def classify_batch(
    study_id: str,
    study_name: str,
    table: ParsedTable,
    variables: list[dict[str, str]],
) -> tuple[list[LLMVariableConcept], int, int]:
    """Run the LLM agent on a batch of variables, with retry on rate-limit errors.

    Args:
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table (for context).
        variables: The variable subset to classify.

    Returns:
        Tuple of (list of LLMVariableConcept, input_tokens, output_tokens).
    """
    prompt = format_table_prompt(study_id, study_name, table, variables)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await get_agent().run(prompt)
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
                    f"RESPONSE [{table.table_name}]\n{concepts_str}\n"
                    f"  tokens: {usage.input_tokens} in / {usage.output_tokens} out\n"
                    f"{'─'*60}",
                    file=sys.stderr,
                )
            return result.output.variables, usage.input_tokens, usage.output_tokens
        except ModelHTTPError as e:
            if e.status_code == 429 and attempt < MAX_RETRIES:
                wait = 2**attempt  # exponential backoff: 2, 4, 8, 16, 32s
                print(
                    f"    Rate limited, retrying in {wait}s "
                    f"(attempt {attempt}/{MAX_RETRIES})...",
                    file=sys.stderr,
                )
                await asyncio.sleep(wait)
            else:
                raise


async def classify_table_concepts(
    study_id: str,
    study_name: str,
    table: ParsedTable,
) -> tuple[list[dict], int, int]:
    """Classify all variables in a table, chunking into batches if needed.

    Args:
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table to classify.

    Returns:
        Tuple of (list of {name, description, concept} dicts, input_tokens, output_tokens).
    """
    all_vars = table.variables
    all_concepts: list[LLMVariableConcept] = []
    total_in = 0
    total_out = 0

    # Chunk into batches of VARS_PER_BATCH
    for i in range(0, len(all_vars), VARS_PER_BATCH):
        batch = all_vars[i : i + VARS_PER_BATCH]
        concepts, tok_in, tok_out = await classify_batch(
            study_id, study_name, table, batch
        )
        all_concepts.extend(concepts)
        total_in += tok_in
        total_out += tok_out

    # Build lookup: variable name -> description from input data
    desc_by_name = {v["name"]: v.get("description", "") for v in all_vars}

    # Build result: map by variable name for dedup
    result = []
    seen = set()
    for vc in all_concepts:
        if vc.variable_name not in seen:
            seen.add(vc.variable_name)
            result.append({
                "name": vc.variable_name,
                "description": desc_by_name.get(vc.variable_name, ""),
                "concept": vc.concept,
            })

    return result, total_in, total_out


# ---------------------------------------------------------------------------
# Running the agent on a full study
# ---------------------------------------------------------------------------

CONCURRENCY = 10


async def classify_study_concepts(
    study_id: str, tables: list[ParsedTable]
) -> dict:
    """Classify all tables in a study, concurrently.

    Args:
        study_id: The study accession.
        tables: All tables for this study.

    Returns:
        Dict with studyId, studyName, and tables list.
    """
    study_name = tables[0].study_name if tables else study_id
    sorted_tables = sorted(tables, key=lambda t: t.table_name)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _classify_one(
        table: ParsedTable,
    ) -> tuple[ParsedTable, list[dict], int, int]:
        async with semaphore:
            variables, tok_in, tok_out = await classify_table_concepts(
                study_id, study_name, table
            )
            return table, variables, tok_in, tok_out

    results = await asyncio.gather(
        *[_classify_one(t) for t in sorted_tables],
        return_exceptions=True,
    )

    table_results = []
    total_in = 0
    total_out = 0
    errors = 0

    for item in results:
        if isinstance(item, Exception):
            errors += 1
            print(f"    ERROR on table: {item}", file=sys.stderr)
            continue
        table, variables, tok_in, tok_out = item
        total_in += tok_in
        total_out += tok_out

        # Derive unique concepts for this table
        concepts = sorted({v["concept"] for v in variables})

        table_results.append(
            {
                "tableName": table.table_name,
                "datasetId": table.dataset_id,
                "description": table.description or None,
                "concepts": concepts,
                "variables": variables,
            }
        )

    cost = total_in * 0.80 / 1e6 + total_out * 4 / 1e6
    print(
        f"    tokens: {total_in:,} in / {total_out:,} out (${cost:.3f})"
        + (f"  [{errors} errors]" if errors else ""),
        file=sys.stderr,
    )

    return {
        "studyId": study_id,
        "studyName": study_name,
        "tables": table_results,
    }


def write_study_concepts(study_result: dict, output_dir: Path) -> Path:
    """Write per-study concept classification to JSON.

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
# Summary generation
# ---------------------------------------------------------------------------


def generate_summary(output_dir: Path, summary_path: Path) -> None:
    """Aggregate concept statistics across all per-study output files.

    Args:
        output_dir: Directory containing per-study JSON files.
        summary_path: Path to write the summary JSON.
    """
    concept_counts: dict[str, int] = defaultdict(int)
    concept_studies: dict[str, set[str]] = defaultdict(set)
    total_variables = 0

    files = sorted(output_dir.glob("phs*.json"))
    if not files:
        print("No output files found — run classification first.", file=sys.stderr)
        return

    for path in files:
        with open(path) as f:
            data = json.load(f)
        study_id = data["studyId"]
        for table in data["tables"]:
            for var in table["variables"]:
                concept = var["concept"]
                concept_counts[concept] += 1
                concept_studies[concept].add(study_id)
                total_variables += 1

    # Build sorted concept list (by count descending)
    concepts = {}
    for concept in sorted(concept_counts, key=lambda c: -concept_counts[c]):
        concepts[concept] = {
            "count": concept_counts[concept],
            "studyCount": len(concept_studies[concept]),
        }

    summary = {
        "totalVariables": total_variables,
        "totalConcepts": len(concepts),
        "studies": len(files),
        "concepts": concepts,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print(
        f"Summary: {total_variables:,} variables, {len(concepts):,} concepts "
        f"across {len(files)} studies → {summary_path}",
        file=sys.stderr,
    )

    # Print top 20
    print("\nTop 20 concepts:", file=sys.stderr)
    for i, (concept, stats) in enumerate(concepts.items()):
        if i >= 20:
            break
        print(
            f"  {stats['count']:>6,} vars  {stats['studyCount']:>4} studies  {concept}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Normalization: merge synonym concepts via LLM
# ---------------------------------------------------------------------------

_normalize_agent: Agent[None, None] | None = None


class ConceptGroup(BaseModel):
    """A group of synonymous concept names with a canonical form."""

    canonical: str = Field(description="The preferred canonical concept name")
    synonyms: list[str] = Field(
        description="Other names that should be mapped to the canonical name"
    )


class NormalizationResult(BaseModel):
    """LLM output for concept normalization."""

    groups: list[ConceptGroup]


NORMALIZE_BATCH_SIZE = 200


async def normalize_concepts(output_dir: Path, normalization_map_path: Path) -> None:
    """Gather all unique concepts, ask LLM to group synonyms, rewrite files.

    Args:
        output_dir: Directory containing per-study JSON files.
        normalization_map_path: Path to write the normalization map.
    """
    # Collect all unique concepts
    all_concepts: set[str] = set()
    files = sorted(output_dir.glob("phs*.json"))
    for path in files:
        with open(path) as f:
            data = json.load(f)
        for table in data["tables"]:
            for var in table["variables"]:
                all_concepts.add(var["concept"])

    sorted_concepts = sorted(all_concepts)
    print(
        f"Found {len(sorted_concepts)} unique concepts across {len(files)} studies",
        file=sys.stderr,
    )

    if len(sorted_concepts) < 2:
        print("Too few concepts to normalize.", file=sys.stderr)
        return

    # Create normalization agent
    normalize_agent = Agent(
        MODEL,
        output_type=NormalizationResult,
        system_prompt=(
            "You are normalizing medical concept names. Given a list of concept names,\n"
            "identify groups that are synonyms or near-synonyms and should be merged.\n\n"
            "Rules:\n"
            "- Only group concepts that truly mean the same measurement/test.\n"
            "- Pick the most standard/recognizable name as canonical.\n"
            "- Do NOT group concepts that are related but distinct "
            '(e.g. "Systolic Blood Pressure" and "Diastolic Blood Pressure" are separate).\n'
            "- Only return groups with 2+ members (concepts with no synonyms can be omitted).\n"
            "- Use Title Case for canonical names.\n"
        ),
        retries=3,
        model_settings={"anthropic_cache_instructions": True},
    )

    # Process in batches
    all_groups: list[dict] = []
    for i in range(0, len(sorted_concepts), NORMALIZE_BATCH_SIZE):
        batch = sorted_concepts[i : i + NORMALIZE_BATCH_SIZE]
        prompt = "Group these concept names by synonym:\n\n"
        prompt += "\n".join(f"- {c}" for c in batch)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await normalize_agent.run(prompt)
                for group in result.output.groups:
                    all_groups.append(
                        {
                            "canonical": group.canonical,
                            "synonyms": group.synonyms,
                        }
                    )
                usage = result.usage()
                print(
                    f"  Batch {i // NORMALIZE_BATCH_SIZE + 1}: "
                    f"{len(result.output.groups)} groups, "
                    f"{usage.input_tokens} in / {usage.output_tokens} out",
                    file=sys.stderr,
                )
                break
            except ModelHTTPError as e:
                if e.status_code == 429 and attempt < MAX_RETRIES:
                    wait = 2**attempt
                    print(f"    Rate limited, retrying in {wait}s...", file=sys.stderr)
                    await asyncio.sleep(wait)
                else:
                    raise

    if not all_groups:
        print("No synonym groups found.", file=sys.stderr)
        return

    # Build mapping: synonym -> canonical
    mapping: dict[str, str] = {}
    for group in all_groups:
        canonical = group["canonical"]
        for syn in group["synonyms"]:
            if syn != canonical:
                mapping[syn] = canonical

    # Write normalization map
    normalization_map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(normalization_map_path, "w") as f:
        json.dump(
            {"groups": all_groups, "mapping": mapping},
            f,
            indent=2,
        )
        f.write("\n")

    print(
        f"\nNormalization map: {len(all_groups)} groups, "
        f"{len(mapping)} synonyms → {normalization_map_path}",
        file=sys.stderr,
    )

    # Apply mapping to all per-study files
    rewritten = 0
    for path in files:
        with open(path) as f:
            data = json.load(f)

        changed = False
        for table in data["tables"]:
            for var in table["variables"]:
                old = var["concept"]
                if old in mapping:
                    var["concept"] = mapping[old]
                    changed = True
            # Rebuild table-level concepts list
            if changed:
                table["concepts"] = sorted({v["concept"] for v in table["variables"]})

        if changed:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            rewritten += 1

    print(f"Rewrote {rewritten}/{len(files)} study files.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Study runner
# ---------------------------------------------------------------------------


async def run_studies(
    study_ids: list[str],
    tables_by_study: dict[str, list[ParsedTable]],
    label: str,
) -> list[dict]:
    """Classify a list of studies and write results.

    Args:
        study_ids: Study IDs to process.
        tables_by_study: All tables grouped by study ID.
        label: Description for progress messages.

    Returns:
        List of result dicts (one per successfully processed study).
    """
    results = []
    total_tables = 0
    total_vars = 0

    for i, study_id in enumerate(study_ids, 1):
        tables = tables_by_study.get(study_id, [])
        if not tables:
            print(
                f"  [{i}/{len(study_ids)}] {study_id}: no tables in cache, skipping",
                file=sys.stderr,
            )
            continue

        n_vars = sum(t.variable_count for t in tables)
        print(
            f"  [{i}/{len(study_ids)}] {study_id} "
            f"({len(tables)} tables, {n_vars:,} vars)...",
            file=sys.stderr,
        )

        try:
            result = await classify_study_concepts(study_id, tables)
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    ERROR: {e} — skipping", file=sys.stderr)
            continue

        write_study_concepts(result, CONCEPT_OUTPUT_DIR)
        n_tables = len(result["tables"])
        n_concepts = len({
            v["concept"]
            for t in result["tables"]
            for v in t["variables"]
        })
        total_tables += n_tables
        total_vars += n_vars
        results.append(result)

        print(
            f"    -> {n_tables} tables, {n_concepts} unique concepts",
            file=sys.stderr,
        )

    print(
        f"\n{label}: {total_tables} tables, {total_vars:,} variables "
        f"across {len(results)} studies.",
        file=sys.stderr,
    )
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for the variable-level concept classification agent."""
    parser = argparse.ArgumentParser(
        description="LLM-based variable-level concept classification for dbGaP tables"
    )
    parser.add_argument(
        "--study", help="Classify only this study ID (e.g. phs000280)"
    )
    parser.add_argument(
        "--table", help="With --study, classify only this one table name"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Classify all studies (including those with existing output)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Regenerate concept-summary.json from existing output files",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Merge synonym concepts via LLM and rewrite output files",
    )
    parser.add_argument(
        "--model",
        help="Override the model (e.g. anthropic:claude-sonnet-4-5-20250929)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Dump each LLM request/response to stderr",
    )
    parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Pydantic Logfire observability",
    )
    parser.add_argument(
        "--logfire-jaeger",
        action="store_true",
        help="Send traces to local Jaeger",
    )
    args = parser.parse_args()

    if args.model:
        global MODEL
        MODEL = args.model
        print(f"Model override: {MODEL}", file=sys.stderr)

    if args.debug:
        global DEBUG
        DEBUG = True

    if args.logfire or args.logfire_jaeger:
        try:
            import logfire
        except ImportError:
            print(
                "ERROR: logfire not installed. "
                "Run: pip install 'pydantic-ai-slim[logfire]'",
                file=sys.stderr,
            )
            sys.exit(1)

        if args.logfire_jaeger:
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = (
                "http://localhost:4318/v1/traces"
            )
            logfire.configure(
                service_name="llm-concept-classify",
                send_to_logfire=False,
            )
            print(
                "Logfire -> Jaeger enabled — "
                "view at http://localhost:16686/search?service=llm-concept-classify",
                file=sys.stderr,
            )
        else:
            logfire.configure()
            print(
                "Logfire enabled — view traces at https://logfire.pydantic.dev",
                file=sys.stderr,
            )

        logfire.instrument_pydantic_ai()

    # Summary-only mode: no API calls needed
    if args.summary:
        generate_summary(CONCEPT_OUTPUT_DIR, SUMMARY_PATH)
        return

    # Normalize-only mode: reads existing output, calls LLM for synonym grouping
    if args.normalize:
        await normalize_concepts(CONCEPT_OUTPUT_DIR, NORMALIZATION_MAP_PATH)
        generate_summary(CONCEPT_OUTPUT_DIR, SUMMARY_PATH)
        return

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

    if args.study:
        if args.table:
            # Filter to a single table for debugging
            study_tables = tables_by_study.get(args.study, [])
            tables_by_study[args.study] = [
                t for t in study_tables if t.table_name == args.table
            ]
            if not tables_by_study[args.study]:
                print(
                    f"ERROR: Table '{args.table}' not found in {args.study}",
                    file=sys.stderr,
                )
                sys.exit(1)
        await run_studies([args.study], tables_by_study, "Done")
    elif args.all:
        study_ids = sorted(tables_by_study.keys())
        await run_studies(study_ids, tables_by_study, "Done")
    else:
        # Incremental: skip studies that already have output files
        existing = {p.stem for p in CONCEPT_OUTPUT_DIR.glob("phs*.json")}
        remaining = sorted(set(tables_by_study.keys()) - existing)
        print(
            f"Found {len(remaining)} studies without concept output "
            f"({len(existing)} already done)...",
            file=sys.stderr,
        )
        await run_studies(remaining, tables_by_study, "Done")


if __name__ == "__main__":
    asyncio.run(main())
