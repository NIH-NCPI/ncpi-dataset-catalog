"""Unit tests for the response-level consent long names on search responses.

Covers ``_collect_consent_long_names`` (one entry per code, only codes the
studies carry, malformed records skipped) and the camelCase serialization of
``SearchResponse.consent_long_names``. Uses small synthetic study dicts.
"""

from __future__ import annotations

from concept_search.api import _collect_consent_long_names
from concept_search.api_models import SearchResponse, SearchTiming
from concept_search.models import QueryModel


class TestCollectConsentLongNames:
    """_collect_consent_long_names maps each code in the studies to its long name."""

    def test_collects_each_code_once(self) -> None:
        """A code shared by several studies appears once in the map."""
        studies = [
            {
                "consentCodes": ["GRU", "HMB"],
                "consentLongNames": {"GRU": "General", "HMB": "Health"},
            },
            {"consentCodes": ["GRU"], "consentLongNames": {"GRU": "General"}},
        ]
        assert _collect_consent_long_names(studies) == {
            "GRU": "General",
            "HMB": "Health",
        }

    def test_keeps_only_codes_the_study_lists(self) -> None:
        """Long names for codes outside ``consentCodes`` are left out."""
        studies = [
            {
                "consentCodes": ["GRU"],
                "consentLongNames": {"GRU": "General", "HMB": "Health"},
            }
        ]
        assert _collect_consent_long_names(studies) == {"GRU": "General"}

    def test_skips_missing_or_malformed_records(self) -> None:
        """Null, non-dict, and non-string values are skipped, not raised."""
        studies = [
            {"consentCodes": ["GRU"]},
            {"consentCodes": ["GRU"], "consentLongNames": None},
            {"consentCodes": ["GRU"], "consentLongNames": ["General"]},
            {"consentCodes": None, "consentLongNames": {"GRU": "General"}},
            {"consentCodes": ["HMB"], "consentLongNames": {"HMB": None}},
            {"consentCodes": ["DS"], "consentLongNames": {"DS": "Disease"}},
        ]
        assert _collect_consent_long_names(studies) == {"DS": "Disease"}

    def test_empty_studies(self) -> None:
        """No studies gives an empty map."""
        assert _collect_consent_long_names([]) == {}


class TestSearchResponseConsentLongNames:
    """SearchResponse serializes the map as ``consentLongNames``."""

    def _build(self, **kwargs: object) -> SearchResponse:
        return SearchResponse(
            message=None,
            query=QueryModel(mentions=[]),
            timing=SearchTiming(lookup_ms=0, pipeline_ms=0, total_ms=0),
            **kwargs,
        )

    def test_serializes_camel_case(self) -> None:
        """The field goes out under its camelCase alias."""
        response = self._build(consent_long_names={"GRU": "General"})
        dumped = response.model_dump(by_alias=True)
        assert dumped["consentLongNames"] == {"GRU": "General"}

    def test_defaults_to_empty(self) -> None:
        """Responses that don't set it (e.g. timeouts) send an empty map."""
        dumped = self._build().model_dump(by_alias=True)
        assert dumped["consentLongNames"] == {}
