"""Unit tests for the conversation-agent tools (no LLM calls).

The tools only read ``ctx.deps``, so a tiny stub context + a fake index exercise
the mutation/aggregation logic directly without standing up a real agent.
"""

from __future__ import annotations

import pytest

from concept_search import conversation_agent
from concept_search.conversation_agent import (
    AgentDeps,
    MentionInput,
    _facet_counts,
    deserialize_history,
    query_catalog,
    resolve_concept,
    serialize_history,
    update_query,
)
from concept_search.models import Facet, QueryModel, ResolveResult


class _FakeStore:
    def query_variables(self, concepts=None, limit=500, study_ids=None, variable_names=None):
        return ([], 0)


class _FakeIndex:
    """Minimal ConceptIndex stand-in capturing query_studies calls."""

    def __init__(self, studies: list[dict] | None = None) -> None:
        self._studies = studies or []
        self.store = _FakeStore()
        self.calls: list[tuple] = []

    def query_studies(self, include, exclude=None):
        self.calls.append((include, exclude))
        return self._studies


class _Ctx:
    """Duck-typed RunContext — the tools only access ``.deps``."""

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps


def _ctx(index: _FakeIndex, query_state: QueryModel | None = None) -> _Ctx:
    return _Ctx(AgentDeps(index=index, query_state=query_state or QueryModel()))


def test_facet_counts_aggregates_list_and_scalar_fields() -> None:
    """_facet_counts counts list facets and scalar focus across studies."""
    studies = [
        {"platforms": ["BDC", "AnVIL"], "focus": "Diabetes"},
        {"platforms": ["BDC"], "focus": "Diabetes"},
        {"platforms": ["KFDRC"], "focus": "Asthma"},
    ]
    counts = _facet_counts(studies, ["platform", "focus"])
    assert counts["platform"] == {"BDC": 2, "AnVIL": 1, "KFDRC": 1}
    assert counts["focus"] == {"Diabetes": 2, "Asthma": 1}


def test_update_query_add_commits_mention_and_summarizes() -> None:
    """update_query(add=...) records the mention and returns a summary."""
    index = _FakeIndex(studies=[{"dbGapId": "phs1", "title": "S1", "focus": "X"}])
    ctx = _ctx(index)
    out = update_query(
        ctx,
        add=[MentionInput(facet=Facet.PLATFORM, original_text="BDC", values=["BDC"])],
    )
    assert ctx.deps.query_state.mentions[0].facet == Facet.PLATFORM
    assert out["total_studies"] == 1
    assert out["active_filters"] == [{"exclude": False, "facet": "platform", "values": ["BDC"]}]


def test_update_query_overwrites_same_facet_and_text() -> None:
    """Adding the same facet+text replaces the prior selection's values."""
    ctx = _ctx(_FakeIndex())
    update_query(ctx, add=[MentionInput(facet=Facet.FOCUS, original_text="dm", values=["a"])])
    update_query(ctx, add=[MentionInput(facet=Facet.FOCUS, original_text="dm", values=["b"])])
    mentions = ctx.deps.query_state.mentions
    assert len(mentions) == 1
    assert mentions[0].values == ["b"]


def test_update_query_remove_drops_by_text() -> None:
    """update_query(remove=...) drops mentions by original_text (case-insensitive)."""
    ctx = _ctx(_FakeIndex())
    update_query(
        ctx, add=[MentionInput(facet=Facet.PLATFORM, original_text="BDC", values=["BDC"])]
    )
    update_query(ctx, remove=["bdc"])
    assert ctx.deps.query_state.mentions == []


def test_update_query_sets_intent() -> None:
    """update_query(intent=...) sets the query intent."""
    ctx = _ctx(_FakeIndex())
    update_query(ctx, intent="variable")
    assert ctx.deps.query_state.intent == "variable"


def test_query_catalog_drop_facets_excludes_constraint() -> None:
    """query_catalog(drop_facets=...) omits that facet from the lookup."""
    state = QueryModel(intent="study")
    index = _FakeIndex(studies=[])
    ctx = _ctx(index, state)
    update_query(
        ctx, add=[MentionInput(facet=Facet.PLATFORM, original_text="BDC", values=["BDC"])]
    )
    index.calls.clear()

    query_catalog(ctx, operation="count", drop_facets=["platform"])

    include, _exclude = index.calls[-1]
    facets_used = {facet for facet, _values in include}
    assert Facet.PLATFORM not in facets_used


def test_query_catalog_facets_groups_results() -> None:
    """query_catalog(operation='facets') returns grouped counts."""
    studies = [{"platforms": ["BDC"]}, {"platforms": ["BDC", "AnVIL"]}]
    ctx = _ctx(_FakeIndex(studies=studies))
    out = query_catalog(ctx, operation="facets", facet_by=["platform"])
    assert out["total_studies"] == 2
    assert out["facets"]["platform"]["BDC"] == 2


@pytest.mark.asyncio()
async def test_resolve_concept_shapes_result(monkeypatch) -> None:
    """resolve_concept wraps run_resolve and returns values/disambiguation/message."""

    async def fake_run_resolve(mention, index, model=None):
        assert mention.facets == [Facet.FOCUS]
        assert mention.text == "diabetes"
        return ResolveResult(values=["mesh:D003920"], disambiguation=[], message=None)

    monkeypatch.setattr(conversation_agent, "run_resolve", fake_run_resolve)
    ctx = _ctx(_FakeIndex())
    out = await resolve_concept(ctx, Facet.FOCUS, "diabetes")
    assert out["values"] == ["mesh:D003920"]
    assert out["disambiguation"] == []
    assert out["message"] is None


def test_history_serialization_round_trips_empty() -> None:
    """serialize/deserialize handle the empty-history base case."""
    assert deserialize_history([]) == []
    assert serialize_history([]) == []
