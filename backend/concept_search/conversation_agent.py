"""Single-agent conversation loop.

One pydantic-ai orchestrator (Sonnet by default) that builds a ``QueryModel``
incrementally via a small set of composable tools, replacing the
Extract→Resolve→Structure→Router state machine for the ``/search``
endpoint. The proven Haiku resolve agent is kept as the ``resolve_concepts``
tool (batched/parallel), so concept grounding (and its evals) are unchanged.

Validated on spike ``noopdog/362``; productionized in slices under epic #365.
This module is the orchestrator + tools; the ``/search`` endpoint that
drives it is wired separately.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits
from pydantic_core import to_jsonable_python

from .index import ConceptIndex
from .mention_constraints import split_mentions
from .models import (
    SINGLE_VALUED_FACETS,
    Facet,
    Intent,
    PendingChoice,
    QueryModel,
    RawMention,
    ResolvedMention,
    ResolveResult,
)
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
    """Per-request dependencies for the orchestrator and its tools.

    ``pending`` holds disambiguation choices the agent has offered but the user
    hasn't resolved yet, so the full state (committed filters + open choices)
    can be injected into every turn.
    """

    index: ConceptIndex
    query_state: QueryModel
    pending: list[PendingChoice] = field(default_factory=list)


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
        counts: Counter[str] = Counter()
        for study in studies:
            raw = study.get(field)
            if isinstance(raw, list):
                counts.update(raw)
            elif raw:
                counts[raw] += 1
        out[facet] = dict(counts.most_common(20))
    return out


def _catalog_facet_counts(index: ConceptIndex, facet_by: list[str]) -> dict:
    """Top values per facet across the WHOLE catalog (no active filters).

    query_studies returns [] for an empty constraint set (by design, so an
    unfiltered search doesn't dump the catalog), so catalog-wide exploration reads
    the store's pre-aggregated facet counts instead.
    """
    if not facet_by:
        return {}
    wanted = set(facet_by)
    out: dict[str, dict[str, int]] = {}
    # get_facet_value_counts is ordered by (facet, count desc), so first-seen
    # insertion order per facet is already highest-count-first.
    for facet, value, count in index.store.get_facet_value_counts():
        if facet in wanted and len(out.setdefault(facet, {})) < 20:
            out[facet][value] = count
    return out


def _count(mentions: list[ResolvedMention], intent: Intent, index: ConceptIndex) -> int:
    """Count the results a set of mentions would return.

    Args:
        mentions: The mentions to execute.
        intent: Query intent, selecting the study or variable count.
        index: ConceptIndex for the lookup.

    Returns:
        Number of matching studies, or variables when the intent is "variable".
    """
    execution = execute_query_model(QueryModel(intent=intent, mentions=mentions), index)
    return execution.total_variable_count if intent == "variable" else len(execution.studies)


def _unsatisfiable_and(
    mentions: list[ResolvedMention],
    intent: Intent,
    index: ConceptIndex,
) -> dict | None:
    """Detect an AND over one single-valued facet that no study can satisfy.

    A study holds exactly one value of a ``SINGLE_VALUED_FACETS`` facet, but it
    is indexed under that value's whole ancestor closure. So two included
    mentions on such a facet are satisfiable when one subsumes the other
    ("cancer and lung cancer" → the lung cancer studies) and impossible when
    they are disjoint ("diabetes and asthma"). Rather than reason over the ISA
    table, ask the index: taken alone, do these mentions match any study?

    Only the conflicting mentions take part in that test — other facets are
    ignored, so an unrelated empty result (a platform filter that excludes
    everything) is never mistaken for an impossible one. The reported counts,
    by contrast, keep the rest of the query applied, so they match what the
    user would actually see.

    Args:
        mentions: The mentions the caller is about to commit.
        intent: Query intent, selecting study or variable counts.
        index: ConceptIndex for the lookups.

    Returns:
        A refusal payload describing the conflict, or None when the commit is
        satisfiable.
    """
    # execute_query_model returns nothing at all for the "ambiguous" intent, which
    # would report every term as 0 studies — numbers the agent is told to show the
    # user. Count as a study query instead; the refusal itself does not depend on
    # intent, only the numbers we hand back do.
    count_intent: Intent = "study" if intent == "ambiguous" else intent

    for facet in sorted(SINGLE_VALUED_FACETS):

        def conflicts(mention: ResolvedMention, facet: Facet = facet) -> bool:
            return mention.facet == facet and not mention.exclude and bool(mention.values)

        conflicting = [m for m in mentions if conflicts(m)]
        if len(conflicting) < 2:
            continue
        if index.query_studies([(facet, m.values) for m in conflicting]):
            continue  # one term subsumes the other — redundant, not impossible
        others = [m for m in mentions if not conflicts(m)]
        merged = ResolvedMention(
            facet=facet,
            original_text=" or ".join(m.original_text for m in conflicting),
            values=list(dict.fromkeys(v for m in conflicting for v in m.values)),
        )
        return {
            "error": "unsatisfiable_and",
            "facet": facet.value,
            # A refusal without a way forward strands a legitimate turn: the user
            # may be *replacing* a term ("change diabetes to asthma"), in which
            # case the old one has to go in the same call. Spell out every exit.
            "hint": (
                "Replacing a term? Pass remove=[old term] together with add=[new term] "
                "in one call. Asking for either term? Commit ONE selection holding both "
                "values. Asking for both at once? Impossible — tell the user, using the "
                "counts above."
            ),
            "if_or": _count([*others, merged], count_intent, index),
            "reason": f"each study has exactly one {facet.value}; these terms are disjoint",
            "terms": {
                m.original_text: _count([*others, m], count_intent, index) for m in conflicting
            },
        }
    return None


def _relaxation_map(query_state: QueryModel, index: ConceptIndex) -> dict[str, int]:
    """For each active (non-excluded) filter, count results if it alone is dropped.

    A deterministic drop-one analysis computed in a single pass — so the model can
    recommend which filter to relax on an empty result without driving the
    exploration through extra query_catalog round-trips. Keyed by each filter's
    original_text. Returns {} when there are fewer than two include filters (the
    breakdown only helps when there's a choice of what to relax).

    Args:
        query_state: The committed query that returned no results.
        index: ConceptIndex for the lookup.

    Returns:
        Mapping of filter original_text -> result count if that filter is dropped.
    """
    includes = [m for m in query_state.mentions if not m.exclude]
    if len(includes) < 2:
        return {}
    excludes = [m for m in query_state.mentions if m.exclude]
    out: dict[str, int] = {}
    for i, mention in enumerate(includes):
        remaining = includes[:i] + includes[i + 1 :] + excludes
        out[mention.original_text] = _count(remaining, query_state.intent, index)
    return out


def _summarize(query_state: QueryModel, index: ConceptIndex) -> dict:
    """Execute the active query and return a summary (no full result rows)."""
    execution = execute_query_model(query_state, index)
    summary = {
        "active_filters": [
            {"exclude": m.exclude, "facet": m.facet.value, "values": m.values}
            for m in query_state.mentions
        ],
        "intent": query_state.intent,
        "sample_studies": [_study_brief(s) for s in execution.studies[:5]],
        "total_studies": len(execution.studies),
        "total_variables": execution.total_variable_count,
    }
    # On an empty result, fold in the drop-one relaxation map so the model can
    # advise which filter to relax in this same turn — no query_catalog probing.
    if not execution.studies and not execution.total_variable_count and query_state.mentions:
        relax = _relaxation_map(query_state, index)
        if relax:
            summary["relaxation"] = relax
    return summary


# --- Tools -----------------------------------------------------------------


def _shape_resolve(request: ResolveRequest, result: ResolveResult) -> dict:
    """Shape one resolve result for the model, tagged with its input."""
    return {
        "disambiguation": [
            {
                "conceptId": d.concept_id,
                "facet": d.facet.value if d.facet else None,
                "label": d.label,
            }
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
    out = [_shape_resolve(m, r) for m, r in zip(mentions, results, strict=True)]
    # Track terms that came back ambiguous as open choices (injected into the
    # next turn's state block so ordinal/"neither" replies have a referent).
    # Merge, don't replace: this call only speaks to the terms it resolved, so
    # keep open choices for untouched terms (from earlier calls/turns), drop any
    # for terms resolved here, and add the ones still ambiguous.
    touched = {m.text.lower() for m in mentions}
    new_pending = [
        PendingChoice(facet=m.facet.value, options=r.disambiguation, text=m.text)
        for m, r in zip(mentions, results, strict=True)
        if r.disambiguation
    ]
    kept = [p for p in ctx.deps.pending if p.text.lower() not in touched]
    ctx.deps.pending = kept + new_pending
    return out


def update_query(
    ctx: RunContext[AgentDeps],
    add: list[MentionInput] | None = None,
    remove: list[str] | None = None,
    intent: Intent | None = None,
    reset: bool = False,
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
        reset: Clear all current filters (and pending choices) before applying —
            use when the user starts a brand-new, unrelated search.

    Returns:
        A summary dict: intent, total_studies, total_variables, active_filters,
        sample_studies. When the result is empty, also includes a ``relaxation``
        map ({filter text: results if dropped}) so you can advise which filter to
        relax without extra exploration.

        Instead of a summary, returns ``{"error": "unsatisfiable_and", ...}`` when
        the commit would AND two disjoint terms on a facet each study holds only
        one of (e.g. focus: "diabetes and asthma"). Nothing is committed. The
        payload carries each term's own count plus ``if_or`` — the count if the
        terms were OR-ed instead. If the user asked for both at once, tell them
        no study can have both and offer those alternatives; if they meant either
        one, re-commit a single mention holding both values.
    """
    deps = ctx.deps
    query_state = deps.query_state
    mentions = [] if reset else list(query_state.mentions)

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

    # Validate before mutating: a refused commit must leave the user's existing
    # filters (and pending choices) exactly as they were, not strand them on a
    # zero-result query.
    conflict = _unsatisfiable_and(mentions, intent or query_state.intent, deps.index)
    if conflict:
        return conflict

    if reset:
        deps.pending = []
    query_state.mentions = mentions
    if intent is not None:
        query_state.intent = intent

    # A term that was just committed or dropped is no longer an open choice.
    touched = {t.lower() for t in (remove or [])} | {i.original_text.lower() for i in (add or [])}
    if touched:
        deps.pending = [p for p in deps.pending if p.text.lower() not in touched]

    return _summarize(query_state, deps.index)


def query_catalog(
    ctx: RunContext[AgentDeps],
    operation: str = "count",
    facet_by: list[str] | None = None,
    drop_facets: list[str] | None = None,
) -> dict:
    """Explore the catalog WITHOUT changing the active query.

    Use to count results, group them by a facet, or list a sample — and for
    empty-result back-off via ``drop_facets``. With no active filters this covers
    the whole catalog via ``count`` and ``facets`` (e.g. operation="facets",
    facet_by=["focus"] to see what diseases exist); ``list`` samples the matched
    studies, so it needs at least one active filter.

    Args:
        operation: "count" (default), "facets" (group-by, needs facet_by), or
            "list" (a sample of the matched studies; needs an active filter).
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

    if not include and not exclude:
        # No active filters → explore the whole catalog from store aggregates,
        # since query_studies([], None) returns [] by design.
        out: dict = {"total_studies": deps.index.store.study_count}
        if operation == "facets":
            out["facets"] = _catalog_facet_counts(deps.index, facet_by or [])
        return out

    studies = deps.index.query_studies(include, exclude or None)
    out = {"total_studies": len(studies)}
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


def _clean_state_field(text: str) -> str:
    """Neutralize characters that would break the bracket-delimited state block.

    Embedded freeform strings (user search text, offered labels) are stripped of
    newlines, ``[``/``]``, and ``"`` so a value like ``studies [phase 2]`` or one
    containing a quote can't split the block, break the ``facet="..."`` quoting,
    or forge a state line. Broader prompt-injection hardening is #364.
    """
    return (
        text.replace("\n", " ")
        .replace("\r", " ")
        .replace("[", "(")
        .replace("]", ")")
        .replace('"', "'")
        .strip()
    )


def _state_preamble(deps: AgentDeps) -> str:
    """Render the full live state (committed filters + open choices) for the model.

    Prepended to every user turn so the model reasons over explicit state rather
    than reconstructing it from prior tool-call history.
    """
    query_state = deps.query_state
    lines: list[str] = []
    if not query_state.mentions:
        lines.append("[Current search: empty — no filters committed yet.]")
    else:
        parts = []
        for m in query_state.mentions:
            prefix = "exclude " if m.exclude else ""
            values = (
                ", ".join(_clean_state_field(v) for v in m.values) if m.values else "(unresolved)"
            )
            parts.append(
                f'{prefix}{m.facet.value}="{_clean_state_field(m.original_text)}" -> {values}'
            )
        lines.append(f"[Current search (intent={query_state.intent}): " + "; ".join(parts) + "]")
    for pending in deps.pending:
        options = "; ".join(
            f"{i + 1}) {_clean_state_field(o.label)}" for i, o in enumerate(pending.options)
        )
        lines.append(f'[Pending choice for "{_clean_state_field(pending.text)}": {options}]')
    return "\n".join(lines)


# Every user message is delivered to the orchestrator fenced inside
# ``<user_input>…</user_input>`` so the system prompt can treat it as untrusted
# data, never instructions (#364). This regex matches any closing-tag variant a
# tokenizer might still read as the fence terminator — case-insensitive, with
# optional internal whitespace/newlines — so a crafted message can't close the
# fence early and have trailing text interpreted as instructions.
_USER_INPUT_CLOSE_TAG = re.compile(r"</\s*user_input\s*>", re.IGNORECASE)

# Cap on model requests (≈ tool-call rounds) per turn. Normal turns use ~2-4
# (resolve + update_query); this bounds a hostile or confused turn from fanning
# out tool calls unbounded (#364). On exceed, pydantic-ai raises
# UsageLimitExceeded; it has no dedicated branch in the /search handler —
# the generic ``except Exception`` catches it and returns a generic error reply.
_MAX_REQUESTS_PER_TURN = 10


def _fence_user_message(message: str) -> str:
    """Wrap the raw user message as untrusted data for the orchestrator.

    The body is delimited by ``<user_input>``/``</user_input>``; the system prompt
    instructs the model to treat everything between them as data describing a
    search, never as instructions. Any closing-tag variant inside the body is
    rewritten to a canonical, defanged form — ``</`` + a zero-width space (U+200B)
    + ``user_input>`` — so the message cannot terminate the fence early. Only the
    matched close-tags are touched (and only their case/whitespace normalized as a
    side effect); the rest of the message is unchanged and fully readable.

    Args:
        message: The raw user message for this turn.

    Returns:
        The message wrapped in a ``<user_input>`` fence with close-tags defanged.
    """
    safe_body = _USER_INPUT_CLOSE_TAG.sub("</\u200buser_input>", message)
    return f"<user_input>\n{safe_body}\n</user_input>"


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
    # The state preamble is trusted (system-generated, already sanitized by
    # _clean_state_field); the user's own message is fenced as untrusted data.
    augmented = f"{_state_preamble(deps)}\n\n{_fence_user_message(message)}"
    result = await agent.run(
        augmented,
        deps=deps,
        message_history=message_history or None,
        usage_limits=UsageLimits(request_limit=_MAX_REQUESTS_PER_TURN),
    )
    return result.output, deps.query_state, result.all_messages()
