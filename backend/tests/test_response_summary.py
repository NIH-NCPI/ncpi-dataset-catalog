"""Unit tests for response_summary module.

Tests the deterministic message-building and empty-result diagnosis logic
using synthetic data — no real index or catalog files needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from concept_search.models import Facet, QueryModel, ResolvedMention
from concept_search.response_summary import (
    QueryClause,
    _oxford_join,
    _render_natural_query,
    _resolve_label,
    _suggest_refinements,
    build_message,
    build_query_structure,
    diagnose_empty_results,
)

# Shared test fixtures

DESCRIPTIONS: dict[str, dict] = {
    "topmed:bp_systolic": {"name": "systolic blood pressure", "description": "Systolic BP"},
    "topmed:bp_diastolic": {"name": "diastolic blood pressure", "description": "Diastolic BP"},
    "ncpi:blood_pressure": {"name": "blood pressure", "description": "Blood pressure measurement"},
    "phenx:smoking_behavior": {"name": "smoking behavior", "description": "Smoking status"},
    "ncpi:subject_age": {"name": "subject age", "description": "Age of subject"},
}


def _mention(
    facet: Facet,
    values: list[str],
    original_text: str = "",
    *,
    exclude: bool = False,
) -> ResolvedMention:
    """Build a minimal ResolvedMention for testing."""
    return ResolvedMention(
        facet=facet,
        values=values,
        original_text=original_text or ", ".join(values),
        exclude=exclude,
    )


def _mock_index(descriptions: dict[str, dict] | None = None) -> MagicMock:
    """Build a mock ConceptIndex with concept descriptions."""
    index = MagicMock()
    index._ensure_concept_descriptions.return_value = descriptions or DESCRIPTIONS
    return index


# --- _resolve_label ---


class TestResolveLabel:
    def test_measurement_concept_lookup(self) -> None:
        label = _resolve_label("ncpi:blood_pressure", Facet.MEASUREMENT, DESCRIPTIONS)
        assert label == "blood pressure"

    def test_unknown_concept_fallback(self) -> None:
        label = _resolve_label("topmed:unknown_thing", Facet.MEASUREMENT, DESCRIPTIONS)
        assert label == "unknown_thing"

    def test_platform_display_name(self) -> None:
        label = _resolve_label("BDC", Facet.PLATFORM, DESCRIPTIONS)
        assert label == "BioData Catalyst"

    def test_platform_unknown_passthrough(self) -> None:
        label = _resolve_label("NewPlatform", Facet.PLATFORM, DESCRIPTIONS)
        assert label == "NewPlatform"

    def test_small_facet_passthrough(self) -> None:
        label = _resolve_label("Whole Genome Sequencing", Facet.DATA_TYPE, DESCRIPTIONS)
        assert label == "Whole Genome Sequencing"


# --- build_query_structure ---


class TestBuildQueryStructure:
    def test_single_mention(self) -> None:
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        assert qs is not None
        assert len(qs.clauses) == 1
        assert qs.clauses[0].labels == ["blood pressure"]
        assert qs.clauses[0].facet == Facet.MEASUREMENT

    def test_multi_facet(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.PLATFORM, ["BDC"], "BDC"),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        assert qs is not None
        assert len(qs.clauses) == 2
        assert qs.clauses[1].labels == ["BioData Catalyst"]

    def test_excluded_mention(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.FOCUS, ["Diabetes"], "diabetes", exclude=True),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        assert qs is not None
        assert qs.clauses[1].exclude is True
        assert qs.clauses[1].operator == "NOT"

    def test_empty_mentions_returns_none(self) -> None:
        qm = QueryModel(mentions=[])
        index = _mock_index()
        assert build_query_structure(qm, index) is None

    def test_unresolved_mentions_skipped(self) -> None:
        qm = QueryModel(mentions=[_mention(Facet.MEASUREMENT, [], "something")])
        index = _mock_index()
        assert build_query_structure(qm, index) is None


# --- build_message ---


class TestBuildMessage:
    def _make_studies(self, n: int) -> list[dict]:
        return [
            {"dbGapId": f"phs{i:06d}", "platforms": ["AnVIL"], "focus": "Cancer"} for i in range(n)
        ]

    def test_measurement_only(self) -> None:
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 33, 0, self._make_studies(33), qm, index)
        assert msg == "Found 33 studies where blood pressure was measured"

    def test_measurement_and_focus(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.FOCUS, ["Cardiovascular Diseases"], "cardiovascular disease"),
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 28, 0, self._make_studies(28), qm, index)
        assert "Found 28 studies with focus Cardiovascular Diseases" in msg
        assert "where blood pressure was measured" in msg

    def test_multiple_measurements_use_are(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.MEASUREMENT, ["phenx:smoking_behavior"], "smoking"),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 10, 0, self._make_studies(10), qm, index)
        assert "were measured" in msg

    def test_variable_intent_with_counts(self) -> None:
        qm = QueryModel(
            intent="variable",
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")],
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 12, 847, [], qm, index)
        assert "12 studies with 847 variables" in msg

    def test_singular_study(self) -> None:
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 1, 0, self._make_studies(1), qm, index)
        assert "Found 1 study" in msg

    def test_with_platform(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.PLATFORM, ["BDC"], "BDC"),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 5, 0, self._make_studies(5), qm, index)
        assert "on BioData Catalyst" in msg
        assert "where blood pressure was measured" in msg

    def test_with_data_type(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.DATA_TYPE, ["Whole Genome Sequencing"], "WGS"),
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 5, 0, self._make_studies(5), qm, index)
        assert "data type is Whole Genome Sequencing" in msg
        assert "blood pressure was measured" in msg

    def test_with_exclude(self) -> None:
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.FOCUS, ["Diabetes"], "diabetes", exclude=True),
            ]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 5, 0, self._make_studies(5), qm, index)
        assert "excluding Diabetes" in msg

    def test_refinement_conditional(self) -> None:
        # <= 10 studies: no refinement
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        msg = build_message(qs, 5, 0, self._make_studies(5), qm, index)
        assert "You could narrow" not in msg

    def test_none_query_structure_returns_empty(self) -> None:
        qm = QueryModel(mentions=[])
        index = _mock_index()
        msg = build_message(None, 0, 0, [], qm, index)
        assert msg == ""

    def test_summary_set_on_structure(self) -> None:
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        qs = build_query_structure(qm, index)
        build_message(qs, 5, 0, self._make_studies(5), qm, index)
        assert qs is not None
        assert qs.summary.startswith("Found 5")


# --- _suggest_refinements ---


class TestSuggestRefinements:
    def test_lte_10_returns_none(self) -> None:
        qm = QueryModel(mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "bp")])
        assert _suggest_refinements(10, [], qm) is None

    def test_suggests_unfiltered_facets(self) -> None:
        studies = [
            {"platforms": ["AnVIL", "BDC"], "focus": "Cancer", "dataTypes": ["WGS"]},
        ] * 15
        qm = QueryModel(mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "bp")])
        result = _suggest_refinements(15, studies, qm)
        assert result is not None
        assert "platform" in result

    def test_caps_at_3(self) -> None:
        studies = [
            {
                "platforms": ["AnVIL", "BDC"],
                "focus": "Cancer",
                "dataTypes": ["WGS", "SNP Array"],
            },
        ] * 15
        qm = QueryModel(mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "bp")])
        result = _suggest_refinements(15, studies, qm)
        assert result is not None
        # Should not have more than 3 suggestions
        # Count commas + "or" to verify
        assert result.count(",") <= 2

    def test_none_when_all_filtered(self) -> None:
        studies = [{"platforms": ["AnVIL"], "focus": "Cancer", "dataTypes": ["WGS"]}] * 15
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "bp"),
                _mention(Facet.PLATFORM, ["AnVIL"], "AnVIL"),
                _mention(Facet.FOCUS, ["Cancer"], "cancer"),
                _mention(Facet.DATA_TYPE, ["WGS"], "WGS"),
                _mention(Facet.CONSENT_CODE, ["GRU"], "general research"),
            ]
        )
        result = _suggest_refinements(15, studies, qm)
        # Only variable-level search might be suggested
        if result is not None:
            assert "variable-level" in result


# --- diagnose_empty_results ---


class TestDiagnoseEmptyResults:
    def test_single_mention_fallback(self) -> None:
        qm = QueryModel(
            mentions=[_mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure")]
        )
        index = _mock_index()
        index.query_studies.return_value = []
        msg = diagnose_empty_results(qm, index)
        assert "No studies found" in msg
        assert "no indexed studies" in msg

    def test_case_a_single_bottleneck(self) -> None:
        """One mention kills everything — dropping it gives results."""
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.PLATFORM, ["KFDRC"], "Kids First"),
            ]
        )
        index = _mock_index()
        # Dropping blood pressure (keeping KFDRC) → 0
        # Dropping KFDRC (keeping blood pressure) → 14
        index.query_studies.side_effect = [
            [],  # drop blood pressure
            [{"dbGapId": f"phs{i:06d}"} for i in range(14)],  # drop KFDRC
        ]
        msg = diagnose_empty_results(qm, index)
        assert "No studies found" in msg
        assert 'Dropping "Kids First" would match 14 studies.' in msg

    def test_case_b_intersection_too_narrow(self) -> None:
        """Each filter alone has results but the combination doesn't."""
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.PLATFORM, ["BDC"], "BDC"),
                _mention(Facet.DATA_TYPE, ["Genomic"], "genomic"),
            ]
        )
        index = _mock_index()
        # All drops yield results
        index.query_studies.side_effect = [
            [{"dbGapId": "phs000001"}] * 8,  # drop blood pressure
            [{"dbGapId": "phs000002"}] * 12,  # drop BDC
            [{"dbGapId": "phs000003"}] * 5,  # drop genomic
        ]
        msg = diagnose_empty_results(qm, index)
        assert "combination is too narrow" in msg
        assert "Try removing" in msg

    def test_case_c_nothing_matches(self) -> None:
        """Every individual mention also returns nothing."""
        qm = QueryModel(
            mentions=[
                _mention(Facet.MEASUREMENT, ["ncpi:blood_pressure"], "blood pressure"),
                _mention(Facet.FOCUS, ["Rare Disease X"], "rare disease X"),
            ]
        )
        index = _mock_index()
        index.query_studies.side_effect = [
            [],  # drop blood pressure
            [],  # drop rare disease X
        ]
        msg = diagnose_empty_results(qm, index)
        assert "Each filter alone returns no results" in msg

    def test_capped_at_3_suggestions(self) -> None:
        """Drop suggestions are capped at 3 even with many mentions."""
        mentions = [
            _mention(Facet.MEASUREMENT, [f"ncpi:concept_{i}"], f"concept {i}") for i in range(5)
        ]
        qm = QueryModel(mentions=mentions)
        index = _mock_index()
        # All drops yield results — case B
        index.query_studies.side_effect = [
            [{"dbGapId": f"phs{i:06d}"}] * (10 - i) for i in range(5)
        ]
        msg = diagnose_empty_results(qm, index)
        # Count "→" arrows to verify cap
        assert msg.count("\u2192") <= 3

    def test_no_values_returns_generic(self) -> None:
        """Mentions with no values get a generic message."""
        qm = QueryModel(mentions=[_mention(Facet.MEASUREMENT, [], "gibberish")])
        index = _mock_index()
        msg = diagnose_empty_results(qm, index)
        assert "Try rephrasing" in msg


# --- _oxford_join ---


class TestOxfordJoin:
    def test_empty(self) -> None:
        assert _oxford_join([]) == ""

    def test_single(self) -> None:
        assert _oxford_join(["a"]) == "a"

    def test_two(self) -> None:
        assert _oxford_join(["a", "b"]) == "a and b"

    def test_three(self) -> None:
        assert _oxford_join(["a", "b", "c"]) == "a, b, and c"

    def test_or_conjunction(self) -> None:
        assert _oxford_join(["a", "b", "c"], "or") == "a, b, or c"


# --- _render_natural_query ---


class TestRenderNaturalQuery:
    def test_measurements_only(self) -> None:
        clauses = [
            QueryClause(Facet.MEASUREMENT, ["blood pressure"]),
            QueryClause(Facet.MEASUREMENT, ["smoking"]),
        ]
        result = _render_natural_query(clauses, "study", count_prefix="Found 10 studies")
        assert "where blood pressure and smoking were measured" in result

    def test_focus_and_measurement(self) -> None:
        clauses = [
            QueryClause(Facet.FOCUS, ["Cardiovascular Diseases"]),
            QueryClause(Facet.MEASUREMENT, ["blood pressure"]),
        ]
        result = _render_natural_query(clauses, "study", count_prefix="Found 5 studies")
        assert "with focus Cardiovascular Diseases" in result
        assert "where blood pressure was measured" in result

    def test_data_type_and_measurement(self) -> None:
        clauses = [
            QueryClause(Facet.DATA_TYPE, ["Whole Genome Sequencing"]),
            QueryClause(Facet.MEASUREMENT, ["BMI"]),
        ]
        result = _render_natural_query(clauses, "study", count_prefix="Found 5 studies")
        assert "data type is Whole Genome Sequencing" in result
        assert "BMI was measured" in result

    def test_with_platform(self) -> None:
        clauses = [
            QueryClause(Facet.MEASUREMENT, ["blood pressure"]),
            QueryClause(Facet.PLATFORM, ["BioData Catalyst"]),
        ]
        result = _render_natural_query(clauses, "study", count_prefix="Found 5 studies")
        assert "on BioData Catalyst" in result
        assert "where blood pressure was measured" in result

    def test_with_exclude(self) -> None:
        clauses = [
            QueryClause(Facet.MEASUREMENT, ["blood pressure"]),
            QueryClause(Facet.FOCUS, ["diabetes"], exclude=True, operator="NOT"),
        ]
        result = _render_natural_query(clauses, "study", count_prefix="Found 5 studies")
        assert "excluding diabetes" in result

    def test_focus_only(self) -> None:
        clauses = [QueryClause(Facet.FOCUS, ["Cancer"])]
        result = _render_natural_query(clauses, "study", count_prefix="Found 12 studies")
        assert result == "Found 12 studies with focus Cancer"
