"""LLM-based classification agent for dbGaP dataset tables.

Uses Pydantic AI with Claude to evaluate tables against RULES.md and produce
rule file JSON, enabling comparison against hand-written rules and scaling
to all ~2,870 studies.

Usage:
    pip install "pydantic-ai-slim[anthropic]"
    export ANTHROPIC_API_KEY='...'

    python llm_classify.py --study phs000007        # One study
    python llm_classify.py --compare                 # Run 36 reviewed, compare to hand-written
    python llm_classify.py --all                     # All studies
    python llm_classify.py                           # Only unreviewed studies (no existing rule file)

Observability:
    pip install "pydantic-ai-slim[logfire]"
    logfire auth                                     # One-time login
    python llm_classify.py --logfire --study phs000343   # View at logfire.pydantic.dev
    python llm_classify.py --debug --study phs000343     # Dump request/response to stderr
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Clear Claude Code sandbox proxy vars — they interfere with httpx/Anthropic API calls
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from classify import load_rules, match_table
from models import ParsedTable, Rule, RuleFile
from parse_var_reports import CACHE_FILE, load_cache

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

RULES_MD_PATH = SCRIPT_DIR / "RULES.md"
RULES_DIR = SCRIPT_DIR / "rules"
LLM_OUTPUT_DIR = SCRIPT_DIR / "output" / "llm-rules"

# Set via --debug flag; when True, dump each request/response to stderr
DEBUG = False

# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------


class TableVerdict(BaseModel):
    """LLM's classification decision for a single table."""

    table_name: str = Field(description="Exact table name")
    classify: bool = Field(
        description="True if this table qualifies for Phase 1 classification"
    )
    measure: str | None = Field(
        default=None, description="Kebab-case measure slug (required if classify=True)"
    )
    domain: str | None = Field(
        default=None, description="Title-case domain name (required if classify=True)"
    )
    rationale: str = Field(
        description="If classified: abbreviation meanings, variable evidence, and traps. "
        "If skipped: why it was skipped (e.g. 'Survey instrument', 'Mixed visit table')."
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    """Read RULES.md and append task-specific instructions."""
    rules_md = RULES_MD_PATH.read_text()
    instructions = """
## Your Task

You are a classification agent. You will be given ONE table at a time from a
dbGaP study (with its name, description, and variable list). Run the 5-prompt
decision checklist above and return your verdict.

**Instructions:**

1. Set `classify=True` if the table passes ALL 5 prompts. Set `classify=False`
   if it fails any prompt.
2. If `classify=True`, set `measure` (kebab-case slug) and `domain` (title case).
   Use the existing measures list when possible. Only propose a new measure if
   no existing one fits AND the table clearly meets the single-procedure test.
3. The `rationale` field is ALWAYS required. If classified: explain what the
   abbreviation/prefix means, which variables confirm the measure, and any traps.
   If skipped: explain why (e.g. "Survey instrument", "Mixed visit table",
   "Demographics/admin data").
4. Do NOT classify surveys, questionnaires, demographics, medical history,
   medications, mixed visit tables, or clinical exam composites.
5. ALWAYS verify against variable names, not just the table name. A table named
   "Epigenomic" might actually contain CBC hematology data.
6. Many tables will not qualify — returning `classify=False` is expected and correct.
"""
    return rules_md + "\n" + instructions


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_agent: Agent[None, TableVerdict] | None = None


MODEL = "anthropic:claude-haiku-4-5"


def get_agent() -> Agent[None, TableVerdict]:
    """Return the shared Agent instance, creating it on first call."""
    global _agent
    if _agent is None:
        _agent = Agent(
            MODEL,
            output_type=TableVerdict,
            system_prompt=build_system_prompt(),
            retries=3,
            model_settings={"anthropic_cache_instructions": True},
        )
    return _agent

# ---------------------------------------------------------------------------
# Building the user message for a single table
# ---------------------------------------------------------------------------


MAX_VARS_PER_TABLE = 200


def format_table_prompt(study_id: str, study_name: str, table: ParsedTable) -> str:
    """Format a single table into the user message sent to the agent.

    Args:
        study_id: The study accession (e.g. phs000007).
        study_name: Human-readable study name.
        table: The ParsedTable to evaluate.

    Returns:
        Formatted string with the table's metadata and variables.
    """
    desc = table.description if table.description else "(none)"

    # Build variable list with descriptions
    shown = table.variables[:MAX_VARS_PER_TABLE]
    var_lines = []
    for v in shown:
        name = v["name"]
        d = v.get("description")
        var_lines.append(f"  {name}: {d}" if d else f"  {name}")
    if len(table.variables) > MAX_VARS_PER_TABLE:
        var_lines.append(f"  ... ({table.variable_count} total)")
    vars_block = "\n".join(var_lines)

    return (
        f"Study: {study_id} — {study_name}\n\n"
        f"TABLE: {table.table_name}  ({table.variable_count:,} vars)\n"
        f"DESCRIPTION: {desc}\n"
        f"VARIABLES:\n{vars_block}"
    )


# ---------------------------------------------------------------------------
# Running the agent on a study
# ---------------------------------------------------------------------------


MAX_RETRIES = 5


async def classify_table(
    study_id: str, study_name: str, table: ParsedTable
) -> tuple[TableVerdict, int, int]:
    """Run the LLM agent on a single table, with retry on rate-limit errors.

    Args:
        study_id: The study accession.
        study_name: Human-readable study name.
        table: The table to evaluate.

    Returns:
        Tuple of (TableVerdict, input_tokens, output_tokens).
    """
    prompt = format_table_prompt(study_id, study_name, table)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await get_agent().run(prompt)
            usage = result.usage()
            if DEBUG:
                print(
                    f"\n{'─'*60}\n"
                    f"REQUEST  [{table.table_name}]\n{prompt}\n"
                    f"{'─'*60}\n"
                    f"RESPONSE [{table.table_name}]\n"
                    f"  classify: {result.output.classify}\n"
                    f"  measure:  {result.output.measure}\n"
                    f"  domain:   {result.output.domain}\n"
                    f"  rational: {result.output.rationale}\n"
                    f"  tokens:   {usage.input_tokens} in / {usage.output_tokens} out\n"
                    f"{'─'*60}",
                    file=sys.stderr,
                )
            return result.output, usage.input_tokens, usage.output_tokens
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


CONCURRENCY = 10


async def classify_study(
    study_id: str, tables: list[ParsedTable]
) -> dict:
    """Classify all tables in a study, concurrently.

    Args:
        study_id: The study accession.
        tables: All tables for this study.

    Returns:
        Dict with studyId, studyName, rules list, and skipped list.
    """
    study_name = tables[0].study_name if tables else study_id
    sorted_tables = sorted(tables, key=lambda t: t.table_name)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _classify_one(table: ParsedTable) -> tuple[ParsedTable, TableVerdict, int, int]:
        async with semaphore:
            verdict, tok_in, tok_out = await classify_table(study_id, study_name, table)
            return table, verdict, tok_in, tok_out

    results = await asyncio.gather(
        *[_classify_one(t) for t in sorted_tables],
        return_exceptions=True,
    )

    rules = []
    skipped = []
    total_in = 0
    total_out = 0
    errors = 0

    for item in results:
        if isinstance(item, Exception):
            errors += 1
            print(f"    ERROR on table: {item}", file=sys.stderr)
            continue
        table, verdict, tok_in, tok_out = item
        total_in += tok_in
        total_out += tok_out

        if verdict.classify and verdict.measure and verdict.domain:
            rules.append({
                "match": {"tableName": f"^{table.table_name}$"},
                "measure": verdict.measure,
                "domain": verdict.domain,
                "rationale": verdict.rationale,
                "description": table.description or None,
            })
        else:
            skipped.append({
                "tableName": table.table_name,
                "reason": verdict.rationale,
            })

    cost = total_in * 0.80 / 1e6 + total_out * 4 / 1e6
    print(
        f"    tokens: {total_in:,} in / {total_out:,} out (${cost:.3f})"
        + (f"  [{errors} errors]" if errors else ""),
        file=sys.stderr,
    )

    return {
        "studyId": study_id,
        "studyName": study_name,
        "rules": rules,
        "skipped": skipped,
    }


def write_llm_rules(study_result: dict, output_dir: Path) -> Path:
    """Write LLM-proposed rules to JSON.

    Args:
        study_result: Dict with studyId, studyName, rules, and skipped.
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
# Comparison logic
# ---------------------------------------------------------------------------


def apply_rules_to_tables(
    tables: list[ParsedTable], rules: list[Rule]
) -> set[tuple[str, str]]:
    """Apply rules to tables and return set of (table_name, measure) pairs.

    Args:
        tables: Tables to classify.
        rules: Rules to apply.

    Returns:
        Set of (table_name, measure) tuples.
    """
    results = set()
    for table in tables:
        rule = match_table(table, rules)
        if rule:
            results.add((table.table_name, rule.measure))
    return results


def load_llm_rules(path: Path) -> list[Rule]:
    """Load rules from an LLM-generated rule file.

    Args:
        path: Path to the JSON file.

    Returns:
        List of Rule objects.
    """
    rf = RuleFile.load(path)
    return rf.rules


def compare_study(
    study_id: str,
    tables: list[ParsedTable],
    hand_rules: list[Rule],
    llm_rules: list[Rule],
) -> dict:
    """Compare hand-written and LLM rules for a single study.

    Args:
        study_id: The study accession.
        tables: All tables for this study.
        hand_rules: Hand-written rules.
        llm_rules: LLM-proposed rules.

    Returns:
        Dict with comparison results.
    """
    hand_matches = apply_rules_to_tables(tables, hand_rules)
    llm_matches = apply_rules_to_tables(tables, llm_rules)

    agreed = hand_matches & llm_matches
    hand_only = hand_matches - llm_matches
    llm_only = llm_matches - hand_matches

    # Find measure disagreements: same table, different measure
    hand_by_table = {t: m for t, m in hand_matches}
    llm_by_table = {t: m for t, m in llm_matches}
    disagreements = {}
    for table_name in set(hand_by_table) & set(llm_by_table):
        if hand_by_table[table_name] != llm_by_table[table_name]:
            disagreements[table_name] = {
                "hand": hand_by_table[table_name],
                "llm": llm_by_table[table_name],
            }

    return {
        "study_id": study_id,
        "agreed": sorted(agreed),
        "hand_only": sorted(hand_only),
        "llm_only": sorted(llm_only),
        "disagreements": disagreements,
    }


def print_comparison(results: list[dict]) -> None:
    """Print comparison results across studies.

    Args:
        results: List of comparison dicts from compare_study().
    """
    total_agreed = 0
    total_hand_only = 0
    total_llm_only = 0
    total_disagreements = 0

    for r in results:
        study_id = r["study_id"]
        n_agreed = len(r["agreed"])
        n_hand = len(r["hand_only"])
        n_llm = len(r["llm_only"])
        n_disagree = len(r["disagreements"])
        total_agreed += n_agreed
        total_hand_only += n_hand
        total_llm_only += n_llm
        total_disagreements += n_disagree

        if n_hand == 0 and n_llm == 0 and n_disagree == 0 and n_agreed == 0:
            continue  # Skip studies with no rules on either side

        print(f"\n{study_id}:")
        print(f"  Agreed: {n_agreed}  Hand-only: {n_hand}  LLM-only: {n_llm}  Disagreements: {n_disagree}")

        if r["agreed"]:
            for table, measure in r["agreed"]:
                print(f"    = {table:40s} -> {measure}")
        if r["hand_only"]:
            for table, measure in r["hand_only"]:
                print(f"    - {table:40s} -> {measure}  (hand only)")
        if r["llm_only"]:
            for table, measure in r["llm_only"]:
                print(f"    + {table:40s} -> {measure}  (LLM only)")
        if r["disagreements"]:
            for table, d in sorted(r["disagreements"].items()):
                print(
                    f"    ! {table:40s}  hand={d['hand']}  llm={d['llm']}"
                )

    total = total_agreed + total_hand_only + total_llm_only
    print(f"\n{'='*60}")
    print(f"TOTALS across {len(results)} studies:")
    print(f"  Agreed:        {total_agreed}")
    print(f"  Hand-only:     {total_hand_only}  (LLM missed)")
    print(f"  LLM-only:      {total_llm_only}  (LLM extras)")
    print(f"  Disagreements: {total_disagreements}  (same table, different measure)")
    if total > 0:
        print(f"  Agreement rate: {total_agreed / total * 100:.1f}%")


# ---------------------------------------------------------------------------
# Main
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
    total_rules = 0

    for i, study_id in enumerate(study_ids, 1):
        tables = tables_by_study.get(study_id, [])
        if not tables:
            print(f"  [{i}/{len(study_ids)}] {study_id}: no tables in cache, skipping", file=sys.stderr)
            continue

        print(f"  [{i}/{len(study_ids)}] {study_id} ({len(tables)} tables)...", file=sys.stderr)

        try:
            result = await classify_study(study_id, tables)
        except (ModelHTTPError, UnexpectedModelBehavior) as e:
            print(f"    ERROR: {e} — skipping", file=sys.stderr)
            continue

        write_llm_rules(result, LLM_OUTPUT_DIR)
        n_rules = len(result["rules"])
        n_skipped = len(result["skipped"])
        total_rules += n_rules
        results.append(result)

        print(f"    -> {n_rules} rules, {n_skipped} skipped", file=sys.stderr)

    print(
        f"\n{label}: {total_rules} total rules across {len(results)} studies.",
        file=sys.stderr,
    )
    return results


async def run_compare(tables_by_study: dict[str, list[ParsedTable]]) -> None:
    """Run comparison mode: classify all reviewed studies, compare to hand-written.

    Args:
        tables_by_study: All tables grouped by study ID.
    """
    rule_files = sorted(RULES_DIR.glob("phs*.json"))
    study_ids = [p.stem for p in rule_files]
    print(f"Comparing {len(study_ids)} studies with hand-written rules...", file=sys.stderr)

    await run_studies(study_ids, tables_by_study, "Compare")

    # Now compare each study's LLM output against hand-written rules
    comparisons = []
    for study_id in study_ids:
        llm_path = LLM_OUTPUT_DIR / f"{study_id}.json"
        if not llm_path.exists():
            continue
        tables = tables_by_study.get(study_id, [])
        if not tables:
            continue

        hand_rules, _ = load_rules(study_id)
        llm_rules = load_llm_rules(llm_path)
        comparisons.append(compare_study(study_id, tables, hand_rules, llm_rules))

    print_comparison(comparisons)


async def main() -> None:
    """Entry point for the LLM classification agent."""
    parser = argparse.ArgumentParser(
        description="LLM-based classification of dbGaP tables into measures"
    )
    parser.add_argument("--study", help="Classify only this study ID (e.g. phs000007)")
    parser.add_argument("--table", help="With --study, classify only this one table name")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run all reviewed studies and compare to hand-written rules",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Classify all studies (including those with existing rules)",
    )
    parser.add_argument(
        "--model",
        help="Override the model (e.g. anthropic:claude-opus-4-6, anthropic:claude-sonnet-4-5-20250929)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Dump each LLM request/response to stderr",
    )
    parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Pydantic Logfire observability (requires: pip install 'pydantic-ai-slim[logfire]')",
    )
    parser.add_argument(
        "--logfire-jaeger",
        action="store_true",
        help="Send traces to local Jaeger (docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest)",
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
            print("ERROR: logfire not installed. Run: pip install 'pydantic-ai-slim[logfire]'", file=sys.stderr)
            sys.exit(1)

        if args.logfire_jaeger:
            import os
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4318/v1/traces"
            logfire.configure(
                service_name="llm-classify",
                send_to_logfire=False,
            )
            print(
                "Logfire -> Jaeger enabled — view at http://localhost:16686/search?service=llm-classify",
                file=sys.stderr,
            )
        else:
            logfire.configure()
            print("Logfire enabled — view traces at https://logfire.pydantic.dev", file=sys.stderr)

        logfire.instrument_pydantic_ai()


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
                print(f"ERROR: Table '{args.table}' not found in {args.study}", file=sys.stderr)
                sys.exit(1)
        await run_studies([args.study], tables_by_study, "Done")
    elif args.compare:
        await run_compare(tables_by_study)
    elif args.all:
        study_ids = sorted(tables_by_study.keys())
        await run_studies(study_ids, tables_by_study, "Done")
    else:
        existing = {p.stem for p in RULES_DIR.glob("phs*.json")}
        unreviewed = sorted(set(tables_by_study.keys()) - existing)
        print(f"Found {len(unreviewed)} unreviewed studies...", file=sys.stderr)
        await run_studies(unreviewed, tables_by_study, "Done")


if __name__ == "__main__":
    asyncio.run(main())
