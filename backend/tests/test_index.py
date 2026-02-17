"""Unit tests for the study store (DuckDB backend).

Covers AND/OR within and between facets, NOT (exclude), and case insensitivity.
Uses small synthetic fixtures — no file I/O or real catalog data.

The tests exercise the ``StudyStore`` protocol so they can verify any backend
implementation (DuckDB today, OpenSearch tomorrow).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from concept_search.models import Facet
from concept_search.store import DuckDBStore, StudyStore


def _make_study(
    dbgap_id: str,
    *,
    platforms: list[str] | None = None,
    focus: str | None = None,
    data_types: list[str] | None = None,
    consent_codes: list[str] | None = None,
    study_designs: list[str] | None = None,
) -> dict:
    """Build a minimal study dict matching the catalog JSON shape."""
    study: dict = {"dbGapId": dbgap_id, "title": f"Study {dbgap_id}"}
    if platforms is not None:
        study["platforms"] = platforms
    if focus is not None:
        study["focus"] = focus
    if data_types is not None:
        study["dataTypes"] = data_types
    if consent_codes is not None:
        study["consentCodes"] = consent_codes
    if study_designs is not None:
        study["studyDesigns"] = study_designs
    return study


def _build_store(
    studies: list[dict],
    study_concepts: dict[str, set[str]] | None = None,
) -> DuckDBStore:
    """Build a DuckDBStore from synthetic data without touching the filesystem."""
    store = DuckDBStore.create_empty()

    facet_field_map = {
        Facet.CONSENT_CODE: "consentCodes",
        Facet.DATA_TYPE: "dataTypes",
        Facet.FOCUS: "focus",
        Facet.PLATFORM: "platforms",
        Facet.STUDY_DESIGN: "studyDesigns",
    }

    for study in studies:
        sid = study["dbGapId"]
        store.load_study(sid, study)
        for facet, field in facet_field_map.items():
            raw = study.get(field)
            if raw is None:
                continue
            values = raw if isinstance(raw, list) else [raw]
            for v in values:
                if v:
                    store.load_facet_value(sid, facet, v)

    if study_concepts:
        for sid, concepts in study_concepts.items():
            for concept in concepts:
                store.load_facet_value(sid, Facet.MEASUREMENT, concept)

    store.finalize()
    return store


# ---------------------------------------------------------------------------
# Fixture: 5 studies across 2 platforms with measurements and focus areas
# ---------------------------------------------------------------------------

STUDIES = [
    _make_study(
        "phs000001",
        platforms=["BDC"],
        focus="Cardiovascular",
        data_types=["WGS"],
        consent_codes=["HMB"],
    ),
    _make_study(
        "phs000002",
        platforms=["BDC"],
        focus="Diabetes",
        data_types=["WGS", "WES"],
        consent_codes=["GRU"],
    ),
    _make_study(
        "phs000003",
        platforms=["AnVIL"],
        focus="Cardiovascular",
        data_types=["WES"],
        consent_codes=["HMB-MDS"],
    ),
    _make_study(
        "phs000004",
        platforms=["AnVIL", "BDC"],
        focus="Cancer",
        data_types=["RNA-Seq"],
        consent_codes=["DS-CVD"],
    ),
    _make_study(
        "phs000005",
        platforms=["CRDC"],
        focus="Cancer",
        data_types=["WGS"],
        consent_codes=["GRU"],
    ),
]

STUDY_CONCEPTS = {
    "phs000001": {"Systolic Blood Pressure", "Diastolic Blood Pressure", "BMI"},
    "phs000002": {"BMI", "HbA1c", "Fasting Glucose"},
    "phs000003": {"Systolic Blood Pressure", "Heart Rate"},
    "phs000004": {"Tumor Size", "White Blood Cell Count"},
    "phs000005": {"Tumor Size", "Survival Time"},
}


@pytest.fixture
def store() -> DuckDBStore:
    """A DuckDBStore with 5 synthetic studies."""
    return _build_store(STUDIES, STUDY_CONCEPTS)


def _ids(studies: list[dict]) -> set[str]:
    """Extract dbGapId set from study list for easy assertion."""
    return {s["dbGapId"] for s in studies}


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_duckdb_store_implements_protocol() -> None:
    """DuckDBStore satisfies the StudyStore protocol."""
    assert isinstance(DuckDBStore(), StudyStore)


# ---------------------------------------------------------------------------
# OR within a single facet
# ---------------------------------------------------------------------------


class TestORWithinFacet:
    """Values within a single facet are OR-ed: match ANY of the values."""

    def test_or_measurement(self, store: DuckDBStore) -> None:
        """Two measurement values — studies with either one match."""
        result = store.query_studies(
            {Facet.MEASUREMENT: ["Systolic Blood Pressure", "HbA1c"]}
        )
        # phs000001 has SBP, phs000002 has HbA1c, phs000003 has SBP
        assert _ids(result) == {"phs000001", "phs000002", "phs000003"}

    def test_or_platform(self, store: DuckDBStore) -> None:
        """Two platforms — studies on either platform match."""
        result = store.query_studies(
            {Facet.PLATFORM: ["BDC", "CRDC"]}
        )
        # phs000001 BDC, phs000002 BDC, phs000004 AnVIL+BDC, phs000005 CRDC
        assert _ids(result) == {"phs000001", "phs000002", "phs000004", "phs000005"}

    def test_or_focus(self, store: DuckDBStore) -> None:
        """Two focus values — studies with either focus match."""
        result = store.query_studies(
            {Facet.FOCUS: ["Cardiovascular", "Diabetes"]}
        )
        assert _ids(result) == {"phs000001", "phs000002", "phs000003"}

    def test_or_data_type(self, store: DuckDBStore) -> None:
        """Two data types — studies with either type match."""
        result = store.query_studies(
            {Facet.DATA_TYPE: ["WGS", "RNA-Seq"]}
        )
        # phs000001 WGS, phs000002 WGS+WES, phs000004 RNA-Seq, phs000005 WGS
        assert _ids(result) == {"phs000001", "phs000002", "phs000004", "phs000005"}


# ---------------------------------------------------------------------------
# AND within a single facet
# ---------------------------------------------------------------------------


def _and_within_facet(
    store: DuckDBStore,
    facet: Facet,
    values: list[str],
) -> list[dict]:
    """Intersect separate single-value lookups to get AND-within-facet.

    The store OR-es values within a single call.  To require ALL values
    (AND), we make one call per value and intersect the result sets.
    """
    result_ids: set[str] | None = None
    all_studies: dict[str, dict] = {}
    for value in values:
        studies = store.query_studies({facet: [value]})
        ids = set()
        for s in studies:
            ids.add(s["dbGapId"])
            all_studies[s["dbGapId"]] = s
        if result_ids is None:
            result_ids = ids
        else:
            result_ids &= ids
    if not result_ids:
        return []
    return [all_studies[sid] for sid in sorted(result_ids)]


class TestANDWithinFacet:
    """AND within a facet: studies must have ALL requested values."""

    def test_and_measurements_both_present(self, store: DuckDBStore) -> None:
        """Studies with BOTH SBP AND BMI."""
        result = _and_within_facet(
            store, Facet.MEASUREMENT, ["Systolic Blood Pressure", "BMI"]
        )
        # phs000001: SBP + BMI yes
        # phs000002: BMI only
        # phs000003: SBP only
        assert _ids(result) == {"phs000001"}

    def test_and_measurements_no_study_has_both(self, store: DuckDBStore) -> None:
        """No study has BOTH HbA1c AND Heart Rate."""
        result = _and_within_facet(
            store, Facet.MEASUREMENT, ["HbA1c", "Heart Rate"]
        )
        assert result == []

    def test_and_measurements_three_values(self, store: DuckDBStore) -> None:
        """Studies with SBP AND DBP AND BMI — only phs000001."""
        result = _and_within_facet(
            store,
            Facet.MEASUREMENT,
            ["Systolic Blood Pressure", "Diastolic Blood Pressure", "BMI"],
        )
        assert _ids(result) == {"phs000001"}

    def test_and_data_types(self, store: DuckDBStore) -> None:
        """Studies with BOTH WGS AND WES — only phs000002."""
        result = _and_within_facet(
            store, Facet.DATA_TYPE, ["WGS", "WES"]
        )
        assert _ids(result) == {"phs000002"}

    def test_or_vs_and_within_measurement(self, store: DuckDBStore) -> None:
        """Demonstrate that query_studies OR-es within a facet,
        while _and_within_facet AND-es."""
        or_result = store.query_studies(
            {Facet.MEASUREMENT: ["Systolic Blood Pressure", "BMI"]}
        )
        and_result = _and_within_facet(
            store, Facet.MEASUREMENT, ["Systolic Blood Pressure", "BMI"]
        )
        # OR: phs000001 (both), phs000002 (BMI), phs000003 (SBP)
        assert _ids(or_result) == {"phs000001", "phs000002", "phs000003"}
        # AND: only phs000001 (has both)
        assert _ids(and_result) == {"phs000001"}
        # AND is always a subset of OR
        assert _ids(and_result) <= _ids(or_result)


# ---------------------------------------------------------------------------
# AND between facets
# ---------------------------------------------------------------------------


class TestANDBetweenFacets:
    """Different facets are AND-ed: studies must match ALL facet constraints."""

    def test_measurement_and_platform(self, store: DuckDBStore) -> None:
        """Blood pressure AND BDC — only studies satisfying both."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["Systolic Blood Pressure"],
            Facet.PLATFORM: ["BDC"],
        })
        # phs000001 has SBP + BDC; phs000003 has SBP but is AnVIL only
        assert _ids(result) == {"phs000001"}

    def test_focus_and_data_type(self, store: DuckDBStore) -> None:
        """Cancer focus AND WGS — only phs000005."""
        result = store.query_studies({
            Facet.FOCUS: ["Cancer"],
            Facet.DATA_TYPE: ["WGS"],
        })
        # phs000004 is Cancer but RNA-Seq; phs000005 is Cancer + WGS
        assert _ids(result) == {"phs000005"}

    def test_three_facets(self, store: DuckDBStore) -> None:
        """Measurement AND platform AND focus — narrow intersection."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["BMI"],
            Facet.PLATFORM: ["BDC"],
            Facet.FOCUS: ["Cardiovascular"],
        })
        # phs000001: BMI + BDC + Cardiovascular yes
        # phs000002: BMI + BDC + Diabetes no (wrong focus)
        assert _ids(result) == {"phs000001"}

    def test_and_empty_intersection(self, store: DuckDBStore) -> None:
        """No study satisfies all constraints — empty result."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["Tumor Size"],
            Facet.PLATFORM: ["BDC"],
            Facet.FOCUS: ["Diabetes"],
        })
        assert result == []


# ---------------------------------------------------------------------------
# OR within + AND between (combined)
# ---------------------------------------------------------------------------


class TestORWithinANDBetween:
    """OR within facets combined with AND between facets."""

    def test_or_measurements_and_platform(self, store: DuckDBStore) -> None:
        """(SBP OR HbA1c) AND BDC."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["Systolic Blood Pressure", "HbA1c"],
            Facet.PLATFORM: ["BDC"],
        })
        # phs000001: SBP + BDC yes
        # phs000002: HbA1c + BDC yes
        # phs000003: SBP + AnVIL no
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_or_platforms_and_focus(self, store: DuckDBStore) -> None:
        """Cancer AND (BDC OR CRDC)."""
        result = store.query_studies({
            Facet.FOCUS: ["Cancer"],
            Facet.PLATFORM: ["BDC", "CRDC"],
        })
        # phs000004: Cancer + BDC yes
        # phs000005: Cancer + CRDC yes
        assert _ids(result) == {"phs000004", "phs000005"}

    def test_or_both_facets(self, store: DuckDBStore) -> None:
        """(SBP OR BMI) AND (BDC OR AnVIL)."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["Systolic Blood Pressure", "BMI"],
            Facet.PLATFORM: ["BDC", "AnVIL"],
        })
        # phs000001: SBP+BMI, BDC yes
        # phs000002: BMI, BDC yes
        # phs000003: SBP, AnVIL yes
        # phs000004: neither SBP nor BMI no
        assert _ids(result) == {"phs000001", "phs000002", "phs000003"}


# ---------------------------------------------------------------------------
# NOT (exclude) — single query_studies call with include + exclude
# ---------------------------------------------------------------------------


class TestNOTExclude:
    """Exclude logic: include constraints minus exclude constraints in one call."""

    def test_exclude_platform(self, store: DuckDBStore) -> None:
        """Blood pressure studies NOT on AnVIL."""
        result = store.query_studies(
            include={Facet.MEASUREMENT: ["Systolic Blood Pressure"]},
            exclude={Facet.PLATFORM: ["AnVIL"]},
        )
        # phs000001: SBP + BDC yes (not AnVIL)
        # phs000003: SBP + AnVIL no (excluded)
        assert _ids(result) == {"phs000001"}

    def test_exclude_focus(self, store: DuckDBStore) -> None:
        """BDC studies NOT Cancer."""
        result = store.query_studies(
            include={Facet.PLATFORM: ["BDC"]},
            exclude={Facet.FOCUS: ["Cancer"]},
        )
        # BDC: phs000001, phs000002, phs000004
        # phs000004 is Cancer -> excluded
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_exclude_measurement(self, store: DuckDBStore) -> None:
        """Cancer studies NOT with Tumor Size."""
        result = store.query_studies(
            include={Facet.FOCUS: ["Cancer"]},
            exclude={Facet.MEASUREMENT: ["Tumor Size"]},
        )
        # Cancer: phs000004, phs000005 — both have Tumor Size -> all excluded
        assert result == []

    def test_exclude_no_overlap(self, store: DuckDBStore) -> None:
        """Exclude that doesn't overlap with includes — no effect."""
        result = store.query_studies(
            include={Facet.FOCUS: ["Diabetes"]},
            exclude={Facet.PLATFORM: ["CRDC"]},
        )
        # Diabetes: phs000002 (BDC) — CRDC exclude doesn't touch it
        assert _ids(result) == {"phs000002"}

    def test_exclude_with_and(self, store: DuckDBStore) -> None:
        """(BMI AND BDC) NOT Cardiovascular."""
        result = store.query_studies(
            include={Facet.MEASUREMENT: ["BMI"], Facet.PLATFORM: ["BDC"]},
            exclude={Facet.FOCUS: ["Cardiovascular"]},
        )
        # BMI + BDC: phs000001, phs000002
        # phs000001 is Cardiovascular -> excluded
        assert _ids(result) == {"phs000002"}


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    """All lookups should be case-insensitive."""

    def test_measurement_lowercase(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            {Facet.MEASUREMENT: ["systolic blood pressure"]}
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_measurement_uppercase(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            {Facet.MEASUREMENT: ["SYSTOLIC BLOOD PRESSURE"]}
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_measurement_mixed_case(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            {Facet.MEASUREMENT: ["sYsToLiC bLoOd PrEsSuRe"]}
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_platform_lowercase(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            {Facet.PLATFORM: ["bdc"]}
        )
        assert _ids(result) == {"phs000001", "phs000002", "phs000004"}

    def test_focus_mixed_case(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            {Facet.FOCUS: ["cAnCeR"]}
        )
        assert _ids(result) == {"phs000004", "phs000005"}

    def test_case_insensitive_and(self, store: DuckDBStore) -> None:
        """Case insensitivity works across AND-ed facets."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["bmi"],
            Facet.PLATFORM: ["anvil"],
        })
        # phs000001: BMI + BDC, phs000002: BMI + BDC — neither on AnVIL
        assert result == []

    def test_case_insensitive_or_and_combined(self, store: DuckDBStore) -> None:
        """Mixed case in OR values with AND between facets."""
        result = store.query_studies({
            Facet.MEASUREMENT: ["SYSTOLIC BLOOD PRESSURE", "hba1c"],
            Facet.PLATFORM: ["bdc"],
        })
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_case_insensitive_exclude(self, store: DuckDBStore) -> None:
        """Exclude matching is also case-insensitive."""
        result = store.query_studies(
            include={Facet.PLATFORM: ["bdc"]},
            exclude={Facet.FOCUS: ["CANCER"]},
        )
        assert _ids(result) == {"phs000001", "phs000002"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Empty inputs, no matches, single study results."""

    def test_empty_facet_values(self, store: DuckDBStore) -> None:
        """Empty values list for a facet — should return nothing."""
        result = store.query_studies({Facet.MEASUREMENT: []})
        assert result == []

    def test_no_matching_value(self, store: DuckDBStore) -> None:
        """Value that doesn't exist in the store."""
        result = store.query_studies(
            {Facet.MEASUREMENT: ["Nonexistent Concept"]}
        )
        assert result == []

    def test_empty_dict(self, store: DuckDBStore) -> None:
        """Empty include dict."""
        result = store.query_studies({})
        assert result == []

    def test_single_study_match(self, store: DuckDBStore) -> None:
        """Only one study has Fasting Glucose."""
        result = store.query_studies(
            {Facet.MEASUREMENT: ["Fasting Glucose"]}
        )
        assert _ids(result) == {"phs000002"}

    def test_results_sorted_by_id(self, store: DuckDBStore) -> None:
        """Results should be sorted by dbGapId."""
        result = store.query_studies(
            {Facet.PLATFORM: ["BDC"]}
        )
        ids = [s["dbGapId"] for s in result]
        assert ids == sorted(ids)

    def test_study_count(self, store: DuckDBStore) -> None:
        """study_count reflects the number of loaded studies."""
        assert store.study_count == 5

    def test_returned_study_has_full_data(self, store: DuckDBStore) -> None:
        """Returned study dicts contain the original fields."""
        result = store.query_studies(
            {Facet.MEASUREMENT: ["Fasting Glucose"]}
        )
        assert len(result) == 1
        study = result[0]
        assert study["dbGapId"] == "phs000002"
        assert study["title"] == "Study phs000002"
        assert study["platforms"] == ["BDC"]
        assert study["focus"] == "Diabetes"


# ---------------------------------------------------------------------------
# DuckDB cache persistence (save / load)
# ---------------------------------------------------------------------------


class TestDuckDBPersistence:
    """Save to file, load from file, and verify queries still work."""

    def test_save_and_load(self, store: DuckDBStore, tmp_path) -> None:
        """Round-trip: save to file, load, query gives same results."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        assert db_file.exists()

        loaded = DuckDBStore.load_from_file(db_file)
        # Same study count
        assert loaded.study_count == store.study_count
        # Same query results
        result = loaded.query_studies(
            {Facet.MEASUREMENT: ["Systolic Blood Pressure"]}
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_loaded_store_supports_and(self, store: DuckDBStore, tmp_path) -> None:
        """AND between facets works on a loaded store."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.query_studies({
            Facet.MEASUREMENT: ["BMI"],
            Facet.PLATFORM: ["BDC"],
        })
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_loaded_store_supports_exclude(self, store: DuckDBStore, tmp_path) -> None:
        """Exclude logic works on a loaded store."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.query_studies(
            include={Facet.PLATFORM: ["BDC"]},
            exclude={Facet.FOCUS: ["Cancer"]},
        )
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_get_facet_value_counts(self, store: DuckDBStore) -> None:
        """get_facet_value_counts returns (facet, value, count) tuples."""
        counts = store.get_facet_value_counts()
        assert len(counts) > 0
        # Each entry is (facet_str, value_str, int_count)
        for facet_str, value, count in counts:
            assert isinstance(facet_str, str)
            assert isinstance(value, str)
            assert isinstance(count, int)
            assert count > 0

    def test_facet_value_counts_preserve_case(self, store: DuckDBStore) -> None:
        """get_facet_value_counts returns original-case values."""
        counts = store.get_facet_value_counts()
        values = {v for _, v, _ in counts}
        # These should be original case, not lowered
        assert "Systolic Blood Pressure" in values
        assert "BDC" in values
        assert "Cardiovascular" in values
