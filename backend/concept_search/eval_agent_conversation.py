"""Multi-turn eval harness for the conversation agent (spike #362).

Runs scripted conversations against ``run_conversation`` and checks the committed
``QueryModel`` and replies. Multi-turn doesn't fit the single-Case pydantic_evals
model, so this is a small custom runner. Calls the Anthropic API — run manually:

    uv run python -m concept_search.eval_agent_conversation

``eval_resolve.py`` still guards concept-grounding quality (the resolve agent is
unchanged); these scenarios cover the new orchestration: routing, small-facet
mapping, exclusions, disambiguation answers, refine/remove, and back-off.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .conversation_agent import AgentDeps, run_conversation
from .index import get_index
from .models import Facet, QueryModel


@dataclass
class Scenario:
    """A scripted multi-turn conversation plus a check on the final state."""

    name: str
    turns: list[str]
    check: Callable[[QueryModel, list[str]], tuple[bool, str]]


def _facets(q: QueryModel) -> list[str]:
    return [m.facet.value for m in q.mentions]


def _has(q: QueryModel, facet: Facet) -> bool:
    return any(m.facet == facet for m in q.mentions)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="fresh-study-with-small-facet",
        turns=["diabetes studies on BDC"],
        check=lambda q, _r: (
            _has(q, Facet.PLATFORM) and _has(q, Facet.FOCUS),
            f"facets={_facets(q)}",
        ),
    ),
    Scenario(
        name="exclusion",
        turns=["WGS studies but not pediatric cohorts"],
        check=lambda q, _r: (
            any(m.exclude for m in q.mentions),
            f"mentions={[(m.facet.value, m.exclude) for m in q.mentions]}",
        ),
    ),
    Scenario(
        name="disambiguation-then-select",
        turns=["glucose studies", "the measurement one"],
        check=lambda q, _r: (
            _has(q, Facet.MEASUREMENT),
            f"facets={_facets(q)}",
        ),
    ),
    Scenario(
        name="refine-add-platform",
        turns=["diabetes studies", "only on BDC"],
        check=lambda q, _r: (
            _has(q, Facet.FOCUS) and _has(q, Facet.PLATFORM),
            f"facets={_facets(q)}",
        ),
    ),
    Scenario(
        name="remove-filter",
        turns=["diabetes studies on BDC", "remove the platform filter"],
        check=lambda q, _r: (
            _has(q, Facet.FOCUS) and not _has(q, Facet.PLATFORM),
            f"facets={_facets(q)}",
        ),
    ),
    Scenario(
        name="empty-result-backoff-completes",
        turns=["WGS metabolomics ATAC-seq studies on KFDRC about a rare disease"],
        check=lambda _q, r: (
            bool(r and r[-1].strip()),
            f"reply_len={len(r[-1]) if r else 0}",
        ),
    ),
]


async def _run_scenario(scenario: Scenario) -> tuple[bool, str]:
    """Drive one scenario end-to-end, returning (passed, detail)."""
    deps = AgentDeps(index=get_index(), query_state=QueryModel())
    history: list = []
    replies: list[str] = []
    for message in scenario.turns:
        reply, _query_state, history = await run_conversation(
            message, deps, message_history=history
        )
        replies.append(reply)
    return scenario.check(deps.query_state, replies)


async def run_evals() -> None:
    """Run all scenarios and print a report."""
    passed = 0
    for scenario in SCENARIOS:
        try:
            ok, detail = await _run_scenario(scenario)
        except Exception as exc:  # noqa: BLE001 — eval harness: report, don't crash
            ok, detail = False, f"error: {type(exc).__name__}: {exc}"
        passed += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {scenario.name}: {detail}")
    print(f"\n{passed}/{len(SCENARIOS)} scenarios passed")


def main() -> None:
    """CLI entry point for the conversation-agent evals."""
    backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(backend_dir / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — skipping agent conversation evals.")
        return
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
