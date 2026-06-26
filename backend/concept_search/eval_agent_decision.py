"""Decision evals for the conversation agent (spike #362).

Two questions a spike must answer before promoting ``/search/agent``:

1. **Accuracy vs the production pipeline** — for the same query, does the agent
   return materially the same studies as ``/search``? (The pipeline is the
   trusted baseline.)
2. **Message/result consistency** — does the agent's prose ever contradict the
   result counts (the "0 studies / good news" failure)? Scored by a Haiku judge.

Calls the Anthropic API (pipeline + agent + judge). Run manually:

    uv run python -m concept_search.eval_agent_decision

Uses unambiguous single-turn queries so the agent commits a query rather than
asking a disambiguation question (which would legitimately differ from the
pipeline). Multi-turn / router-case coverage is a separate eval.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from .conversation_agent import AgentDeps, run_conversation
from .index import ConceptIndex, get_index
from .models import QueryModel
from .pipeline import run_pipeline
from .search_execution import execute_query_model

# Unambiguous single-turn queries (no disambiguation expected), spanning facet
# types and including an over-constrained (empty) case.
QUERIES = [
    "diabetes studies",
    "lung cancer studies on BDC",
    "asthma studies with WGS",
    "studies about Parkinson disease",
    "studies measuring body mass index",
    "WGS studies on AnVIL",
    "hypertension studies",
    "Hi-C metabolomics studies on KFDRC about Alzheimer disease",
]

ACCURACY_THRESHOLD = 0.7  # Jaccard overlap of study sets to count as a match.

_JUDGE_PROMPT = (
    "You judge whether a search assistant's reply is CONSISTENT with the result "
    "counts it was based on. It is INCONSISTENT if the reply claims studies or "
    "variables were found when both counts are 0, or claims nothing was found "
    "when a count is greater than 0, or states a number that contradicts the "
    "counts. Otherwise it is consistent. Judge only count-consistency, not style."
)


class _Verdict(BaseModel):
    """Judge output for message/result consistency."""

    consistent: bool
    reason: str


_judge: Agent[None, _Verdict] | None = None


def _get_judge() -> Agent[None, _Verdict]:
    """Lazily construct the consistency-judge agent (needs ANTHROPIC_API_KEY)."""
    global _judge  # noqa: PLW0603
    if _judge is None:
        _judge = Agent(
            "anthropic:claude-haiku-4-5-20251001",
            output_type=_Verdict,
            system_prompt=_JUDGE_PROMPT,
            model_settings=ModelSettings(temperature=0.0),
        )
    return _judge


def _study_ids(query_model: QueryModel, index: ConceptIndex) -> set[str]:
    """Execute a query and return its matched study dbGapIds."""
    execution = execute_query_model(query_model, index)
    return {s.get("dbGapId", "") for s in execution.studies}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard overlap of two sets (1.0 when both empty)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def _run_query(query: str, index: ConceptIndex) -> dict:
    """Run one query through both paths and judge the agent's reply."""
    pipeline_model = await run_pipeline(query)
    p_ids = _study_ids(pipeline_model, index)

    deps = AgentDeps(index=index, query_state=QueryModel())
    reply, agent_state, _history = await run_conversation(query, deps)
    a_ids = _study_ids(agent_state, index)

    execution = execute_query_model(agent_state, index)
    verdict = await _get_judge().run(
        f"Query: {query}\n"
        f"total_studies={len(execution.studies)} "
        f"total_variables={execution.total_variable_count}\n"
        f"Assistant reply: {reply}"
    )
    return {
        "agent": len(a_ids),
        "consistent": verdict.output.consistent,
        "jaccard": _jaccard(p_ids, a_ids),
        "pipeline": len(p_ids),
        "query": query,
        "reason": verdict.output.reason,
    }


async def run_evals() -> None:
    """Run the decision evals and print accuracy + consistency reports."""
    index = get_index()
    rows: list[dict] = []
    for query in QUERIES:
        try:
            rows.append(await _run_query(query, index))
        except Exception as exc:  # noqa: BLE001 — eval harness: report, don't crash
            rows.append({"query": query, "error": f"{type(exc).__name__}: {exc}"})

    n = acc_pass = cons_pass = 0
    for r in rows:
        if "error" in r:
            print(f"[ERROR]      {r['query']}: {r['error']}")
            continue
        n += 1
        acc_ok = r["jaccard"] >= ACCURACY_THRESHOLD
        acc_pass += int(acc_ok)
        cons_pass += int(r["consistent"])
        acc = "ACC-OK " if acc_ok else "ACC-DIFF"
        cons = "MSG-OK " if r["consistent"] else "MSG-BAD"
        line = (
            f"[{acc}|{cons}] {r['query']}: "
            f"pipeline={r['pipeline']} agent={r['agent']} jaccard={r['jaccard']:.2f}"
        )
        if not r["consistent"]:
            line += f"\n    inconsistency: {r['reason'][:100]}"
        print(line)

    print(f"\nAccuracy vs pipeline (jaccard >= {ACCURACY_THRESHOLD}): {acc_pass}/{n}")
    print(f"Message/result consistency:                  {cons_pass}/{n}")


def main() -> None:
    """CLI entry point for the decision evals."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — skipping decision evals.")
        return
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
