"""Single-agent conversation loop (spike #362).

One pydantic-ai orchestrator (Sonnet by default) that builds a ``QueryModel``
incrementally via a small set of composable tools, replacing the
Extract→Resolve→Structure→Router state machine for the ``/search/agent``
endpoint. The proven Haiku resolve agent is kept as the ``resolve_concepts``
tool (batched/parallel), so concept grounding (and its evals) are unchanged.

Design: ``docs/DESIGN-agent-loop.md``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.settings import ModelSettings
from pydantic_core import to_jsonable_python

from .index import ConceptIndex
from .mention_constraints import split_mentions
from .models import Facet, Intent, QueryModel, RawMention, ResolvedMention, ResolveResult
from .resolve_agent import run_resolve
from .search_execution import execute_query_model

# Study-dict field backing each facet, for query_catalog aggregation.
# (No SQL GROUP BY exists today — we aggregate from returned study dicts.)
_FACET_STUDY_FIELD = {
    "consentCode": "consentCodes",
    "dataType": "dataTypes",
    "focus": "focus",
    "platform": "platforms",
    "studyDesign": "studyDesigns",
}


@dataclass
class AgentDeps:
    """Per-request dependencies for the orchestrator and its tools."""

    index: ConceptIndex
    query_state: QueryModel


class MentionInput(BaseModel):
    """A single resolved facet selection to add to the query."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    exclude: bool = False
    facet: Facet
    original_text: str
    values: list[str] = Field(default_factory=list)


class ResolveRequest(BaseModel):
    """A single large-facet term to ground."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    facet: Facet
    text: str


def _study_brief(study: dict) -> dict:
    """Project a study dict to a compact summary for the model."""
    return {
        "dbGapId": study.get("dbGapId", ""),
        "focus": study.get("focus"),
        "title": study.get("title", ""),
    }


def _facet_counts(studies: list[dict], facet_by: list[str]) -> dict:
    """Group studies by each facet, returning the top values with counts."""
    out: dict[str, dict[str, int]] = {}
    for facet in facet_by:
        field = _FACET_STUDY_FIELD.get(facet)
        if field is None:
            continue
        counts: dict[str, int] = {}
        for study in studies:
            raw = study.get(field)
            values = raw if isinstance(raw, list) else ([raw] if raw else [])
            for value in values:
                counts[value] = counts.get(value, 0) + 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
        out[facet] = dict(top)
    return out


def _summarize(query_state: QueryModel, index: ConceptIndex) -> dict:
    """Execute the active query and return a summary (no full result rows)."""
    execution = execute_query_model(query_state, index)
    return {
        "active_filters": [
            {"exclude": m.exclude, "facet": m.facet.value, "values": m.values}
            for m in query_state.mentions
        ],
        "intent": query_state.intent,
        "sample_studies": [_study_brief(s) for s in execution.studies[:5]],
        "total_studies": len(execution.studies),
        "total_variables": execution.total_variable_count,
    }


# --- Tools -----------------------------------------------------------------


def _shape_resolve(request: ResolveRequest, result: ResolveResult) -> dict:
    """Shape one resolve result for the model, tagged with its input."""
    return {
        "disambiguation": [
            {"conceptId": d.concept_id, "facet": d.facet, "label": d.label}
            for d in result.disambiguation
        ],
        "facet": request.facet.value,
        "message": result.message,
        "text": request.text,
        "values": result.values,
    }


async def resolve_concepts(
    ctx: RunContext[AgentDeps], mentions: list[ResolveRequest]
) -> list[dict]:
    """Ground one or more LARGE-facet terms into canonical catalog values.

    Pass ALL of a query's large-facet terms in a single call — they are resolved
    concurrently, so batching is much faster than calling this once per term. Use
    for focus (disease/condition), measurement (phenotype/what was measured), and
    consentCode (data-use) — NOT for the small enumerated facets, which you map
    directly via update_query.

    Each result is either resolved ``values`` (commit them with update_query) or
    ``disambiguation`` options to ask the user about (do not guess between them).
    Results are tagged with their ``facet`` and ``text`` so you can match them.

    Args:
        mentions: The large-facet terms to ground (facet + text each).

    Returns:
        One result dict per input, each with ``facet``, ``text``, ``values``,
        ``disambiguation`` (list of {conceptId, facet, label}), and ``message``.
    """
    results = await asyncio.gather(
        *(run_resolve(RawMention(facets=[m.facet], text=m.text), ctx.deps.index) for m in mentions)
    )
    return [_shape_resolve(m, r) for m, r in zip(mentions, results, strict=True)]


def update_query(
    ctx: RunContext[AgentDeps],
    add: list[MentionInput] | None = None,
    remove: list[str] | None = None,
    intent: Intent | None = None,
) -> dict:
    """Commit changes to the active query and return a result summary.

    This is the source of truth for the results the user sees — always record
    selections here. Returns counts, the active filters, and a small sample (not
    full rows).

    Args:
        add: Selections to add. A selection with the same facet + original_text
            overwrites the existing one.
        remove: original_text values to drop (case-insensitive, any facet).
        intent: Set the query intent (study | variable | ambiguous).

    Returns:
        A summary dict: intent, total_studies, total_variables, active_filters,
        sample_studies.
    """
    query_state = ctx.deps.query_state
    mentions = list(query_state.mentions)

    if remove:
        drop = {r.lower() for r in remove}
        mentions = [m for m in mentions if m.original_text.lower() not in drop]

    for item in add or []:
        text_lower = item.original_text.lower()
        mentions = [
            m
            for m in mentions
            if not (m.facet == item.facet and m.original_text.lower() == text_lower)
        ]
        mentions.append(
            ResolvedMention(
                exclude=item.exclude,
                facet=item.facet,
                original_text=item.original_text,
                values=item.values,
            )
        )

    query_state.mentions = mentions
    if intent is not None:
        query_state.intent = intent

    return _summarize(query_state, ctx.deps.index)


def query_catalog(
    ctx: RunContext[AgentDeps],
    operation: str = "count",
    facet_by: list[str] | None = None,
    drop_facets: list[str] | None = None,
) -> dict:
    """Explore the catalog WITHOUT changing the active query.

    Use to count results, group them by a facet, or list a sample — and for
    empty-result back-off via ``drop_facets``. With no active filters this covers
    the whole catalog (e.g. operation="facets", facet_by=["focus"] to see what
    diseases exist).

    Args:
        operation: "count" (default), "facets" (group-by, needs facet_by), or
            "list" (a sample of studies).
        facet_by: Facets to group by for operation="facets" (e.g. ["focus"]).
        drop_facets: Active facets to ignore for this exploration — use to test
            how many results relaxing a filter would yield.

    Returns:
        Dict with ``total_studies`` and, per operation, ``facets`` or
        ``sample_studies``.
    """
    deps = ctx.deps
    drop = {d.lower() for d in (drop_facets or [])}
    mentions = [m for m in deps.query_state.mentions if m.facet.value.lower() not in drop]
    include, exclude = split_mentions(mentions, deps.index)
    studies = deps.index.query_studies(include, exclude or None)

    out: dict = {"total_studies": len(studies)}
    if operation == "facets":
        out["facets"] = _facet_counts(studies, facet_by or [])
    elif operation == "list":
        out["sample_studies"] = [_study_brief(s) for s in studies[:10]]
    return out


# --- Agent singleton -------------------------------------------------------

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "CONVERSATION_PROMPT.md")
_DEFAULT_MODEL = os.getenv("AGENT_ORCHESTRATOR_MODEL", "anthropic:claude-sonnet-4-6")

_agent: Agent[AgentDeps, str] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


def _load_prompt() -> str:
    """Load the orchestrator system prompt."""
    with open(_PROMPT_PATH) as fh:
        return fh.read()


def _get_agent(model: str | None = None) -> Agent[AgentDeps, str]:
    """Get or create the singleton orchestrator agent, rebuilding on model change."""
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    with _lock:
        if _agent is None or model != _agent_model:
            _agent_model = model
            _agent = Agent(
                model,
                deps_type=AgentDeps,
                system_prompt=_load_prompt(),
                tools=[resolve_concepts, update_query, query_catalog],
                model_settings=ModelSettings(
                    anthropic_cache_instructions=True,
                    anthropic_cache_tool_definitions=True,
                    temperature=0.0,
                ),
            )
        return _agent


def deserialize_history(raw: list[dict]) -> list[ModelMessage]:
    """Restore pydantic-ai message history from stored JSON-able dicts."""
    if not raw:
        return []
    return ModelMessagesTypeAdapter.validate_python(raw)


def serialize_history(messages: list[ModelMessage]) -> list[dict]:
    """Serialize pydantic-ai message history to JSON-able dicts for storage."""
    return to_jsonable_python(messages)


async def run_conversation(
    message: str,
    deps: AgentDeps,
    message_history: list[ModelMessage] | None = None,
    model: str | None = None,
) -> tuple[str, QueryModel, list[ModelMessage]]:
    """Run one conversational turn.

    Args:
        message: The user's latest message.
        deps: Per-request deps carrying the ConceptIndex and the mutable
            ``query_state`` the tools build up.
        message_history: Prior pydantic-ai messages (already deserialized).
        model: Optional model override (default: env / Sonnet).

    Returns:
        (reply_text, committed query_state, full message history for persistence).
    """
    agent = _get_agent(model)
    result = await agent.run(message, deps=deps, message_history=message_history or None)
    return result.output, deps.query_state, result.all_messages()
