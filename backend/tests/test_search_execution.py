"""Unit tests for execute_query_model — the shared deterministic lookup."""

from __future__ import annotations

from concept_search.models import Facet, QueryModel, ResolvedMention
from concept_search.search_execution import execute_query_model


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query_variables(self, concepts=None, limit=500, study_ids=None, variable_names=None):
        self.calls.append({"concepts": concepts, "study_ids": study_ids})
        return ([{"variableName": "v1"}], 1)


class _FakeIndex:
    """Minimal ConceptIndex stand-in returning fixed studies."""

    def __init__(self, studies: list[dict]) -> None:
        self._studies = studies
        self.store = _FakeStore()

    def query_studies(self, include, exclude=None):
        return self._studies


def test_blank_study_ids_do_not_trigger_variable_query() -> None:
    """A matched study without dbGapId must not become a '' study-id constraint.

    Regression for #368: previously the blank "" made the empty-constraint gate
    truthy and passed `study_id IN ('')` to query_variables.
    """
    index = _FakeIndex(studies=[{"title": "study with no dbGapId"}])
    query = QueryModel(
        intent="variable",
        mentions=[ResolvedMention(facet=Facet.PLATFORM, original_text="BDC", values=["BDC"])],
    )

    result = execute_query_model(query, index)

    assert result.variable_rows == []
    assert result.total_variable_count == 0
    assert index.store.calls == []  # gate stays empty — query_variables not called


def test_valid_study_ids_pass_through() -> None:
    """Studies with real dbGapIds still flow through as a study-id constraint."""
    index = _FakeIndex(studies=[{"dbGapId": "phs1"}, {"dbGapId": "phs2"}])
    query = QueryModel(
        intent="variable",
        mentions=[ResolvedMention(facet=Facet.PLATFORM, original_text="BDC", values=["BDC"])],
    )

    execute_query_model(query, index)

    assert index.store.calls[-1]["study_ids"] == {"phs1", "phs2"}
