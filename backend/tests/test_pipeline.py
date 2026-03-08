"""Unit tests for pipeline merge logic and API dispatch (no LLM calls)."""

from __future__ import annotations

import pytest

from concept_search.models import Facet, QueryModel, ResolvedMention
from concept_search.pipeline import _merge_with_previous


def _rm(
    facet: Facet,
    text: str,
    values: list[str] | None = None,
    exclude: bool = False,
) -> ResolvedMention:
    """Shorthand for building a ResolvedMention."""
    return ResolvedMention(
        exclude=exclude,
        facet=facet,
        original_text=text,
        values=values or [],
    )


class TestMergeWithPrevious:
    """Tests for _merge_with_previous()."""

    def test_adds_new_mention(self) -> None:
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])]
        )
        new = [_rm(Facet.PLATFORM, "AnVIL", ["AnVIL"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 2
        facets = {m.facet for m in result.mentions}
        assert Facet.FOCUS in facets
        assert Facet.PLATFORM in facets

    def test_empty_previous_returns_new_only(self) -> None:
        previous = QueryModel(mentions=[])
        new = [_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 1
        assert result.mentions[0].original_text == "diabetes"

    def test_duplicate_key_latest_wins(self) -> None:
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "cancer", ["Cancer"], exclude=False)]
        )
        new = [_rm(Facet.FOCUS, "cancer", ["Cancer"], exclude=True)]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 1
        assert result.mentions[0].exclude is True

    def test_preserves_exclude_flags(self) -> None:
        previous = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                _rm(Facet.FOCUS, "pediatric", ["Pediatrics"], exclude=True),
            ]
        )
        new = [_rm(Facet.PLATFORM, "AnVIL", ["AnVIL"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 3
        excluded = [m for m in result.mentions if m.exclude]
        assert len(excluded) == 1
        assert excluded[0].original_text == "pediatric"

    def test_carries_intent_from_new(self) -> None:
        previous = QueryModel(intent="study", mentions=[])
        new: list[ResolvedMention] = []
        result = _merge_with_previous(previous, new, new_intent="variable")
        assert result.intent == "variable"

    def test_keeps_previous_intent_when_new_is_none(self) -> None:
        previous = QueryModel(intent="variable", mentions=[])
        new: list[ResolvedMention] = []
        result = _merge_with_previous(previous, new, new_intent=None)
        assert result.intent == "variable"

    def test_multiple_facets_accumulated(self) -> None:
        previous = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                _rm(Facet.DATA_TYPE, "WGS", ["WGS"]),
            ]
        )
        new = [
            _rm(Facet.PLATFORM, "AnVIL", ["AnVIL"]),
            _rm(Facet.SEX, "female", ["Female"]),
        ]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 4

    def test_same_facet_different_text_both_kept(self) -> None:
        """Two focus mentions with different text should both be kept."""
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])]
        )
        new = [_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 2
