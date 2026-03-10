"""Tests for API-layer consent scope inference and tag expansion."""

from __future__ import annotations

from concept_search.api import _infer_consent_scope, _split_mentions
from concept_search.index import get_index
from concept_search.models import Facet, ResolvedMention


def _mention(
    text: str,
    facet: Facet,
    values: list[str] | None = None,
) -> ResolvedMention:
    return ResolvedMention(
        facet=facet,
        original_text=text,
        values=values or [],
    )


# ---------------------------------------------------------------------------
# _infer_consent_scope
# ---------------------------------------------------------------------------


class TestInferConsentScope:
    def test_no_focus_returns_general(self):
        mentions = [_mention("GRU", Facet.CONSENT_CODE)]
        assert _infer_consent_scope(mentions) == ("general", None)

    def test_non_disease_focus_returns_health(self):
        mentions = [_mention("genomics", Facet.FOCUS, ["Genomics"])]
        assert _infer_consent_scope(mentions) == ("health", None)

    def test_disease_focus_returns_disease(self):
        # "CVD" abbreviation resolves directly
        mentions = [
            _mention("CVD", Facet.FOCUS, ["CVD"]),
        ]
        scope, disease = _infer_consent_scope(mentions)
        assert scope == "disease"
        assert disease == "CVD"

    def test_scans_all_focus_mentions(self):
        """Second focus mention has disease even though first doesn't."""
        mentions = [
            _mention("genomics", Facet.FOCUS, ["Genomics"]),
            _mention("cancer", Facet.FOCUS, ["Cancer"]),
        ]
        scope, disease = _infer_consent_scope(mentions)
        assert scope == "disease"
        assert disease == "CA"

    def test_falls_back_to_original_text(self):
        """If resolved value doesn't match, try original_text."""
        # "Cardiovascular Diseases" (MeSH term) doesn't resolve,
        # but "cardiovascular disease" (original_text) does
        mentions = [
            _mention("cardiovascular disease", Facet.FOCUS, ["Cardiovascular Diseases"]),
        ]
        scope, disease = _infer_consent_scope(mentions)
        assert scope == "disease"
        assert disease == "CVD"

    def test_empty_mentions(self):
        assert _infer_consent_scope([]) == ("general", None)


# ---------------------------------------------------------------------------
# _split_mentions with consent tag expansion
# ---------------------------------------------------------------------------


class TestSplitMentionsConsentExpansion:
    def test_no_npu_tag_expands_to_codes(self):
        """no-npu tag + disease focus → expanded codes without NPU."""
        index = get_index()
        mentions = [
            _mention("cardiovascular disease", Facet.FOCUS, ["Cardiovascular Diseases"]),
            _mention("for-profit", Facet.CONSENT_CODE, ["no-npu"]),
        ]
        include, _exclude = _split_mentions(mentions, index)
        # Find the consent constraint
        consent = [c for c in include if c[0] == Facet.CONSENT_CODE]
        assert len(consent) == 1
        codes = consent[0][1]
        # Should have GRU, HMB, and DS-CVD codes
        assert any(c.startswith("GRU") for c in codes)
        assert any(c.startswith("HMB") for c in codes)
        # No NPU codes
        from concept_search.consent_logic import parse_consent_code
        for code in codes:
            assert "NPU" not in parse_consent_code(code).modifiers

    def test_explicit_tag_expands(self):
        """explicit:GRU tag → GRU variants only."""
        index = get_index()
        mentions = [
            _mention("GRU", Facet.CONSENT_CODE, ["explicit:GRU"]),
        ]
        include, _exclude = _split_mentions(mentions, index)
        consent = [c for c in include if c[0] == Facet.CONSENT_CODE]
        assert len(consent) == 1
        codes = consent[0][1]
        assert all(c.startswith("GRU") for c in codes)
        assert "GRU" in codes

    def test_empty_tags_with_focus_infers_scope(self):
        """Empty consent tags + focus → scope-based expansion."""
        index = get_index()
        mentions = [
            _mention("cancer", Facet.FOCUS, ["Cancer"]),
            _mention("eligible", Facet.CONSENT_CODE, []),
        ]
        include, _exclude = _split_mentions(mentions, index)
        # Empty consent tags with disease focus → disease scope codes
        consent = [c for c in include if c[0] == Facet.CONSENT_CODE]
        assert len(consent) == 1
        codes = consent[0][1]
        assert any(c.startswith("DS-CA") for c in codes)

    def test_non_tag_values_pass_through(self):
        """Regular consent code values (not tags) pass through unchanged."""
        index = get_index()
        mentions = [
            _mention("GRU", Facet.CONSENT_CODE, ["GRU", "GRU-IRB"]),
        ]
        include, _exclude = _split_mentions(mentions, index)
        consent = [c for c in include if c[0] == Facet.CONSENT_CODE]
        assert len(consent) == 1
        assert consent[0][1] == ["GRU", "GRU-IRB"]

    def test_no_index_skips_expansion(self):
        """Without index, tags pass through as-is."""
        mentions = [
            _mention("for-profit", Facet.CONSENT_CODE, ["no-npu"]),
        ]
        include, _exclude = _split_mentions(mentions, None)
        consent = [c for c in include if c[0] == Facet.CONSENT_CODE]
        assert len(consent) == 1
        assert consent[0][1] == ["no-npu"]
