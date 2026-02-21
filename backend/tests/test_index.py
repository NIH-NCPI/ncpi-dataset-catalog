"""Unit tests for the study store (DuckDB backend).

Covers AND/OR within and between facets, NOT (exclude), and case insensitivity.
Uses small synthetic fixtures — no file I/O or real catalog data.

The tests exercise the ``StudyStore`` protocol so they can verify any backend
implementation (DuckDB today, OpenSearch tomorrow).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest.mock
from pathlib import Path

import pytest

from concept_search.api import _build_study_summary
from concept_search.index import _load_demographic_mappings, _normalize_categories
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
            [(Facet.MEASUREMENT, ["Systolic Blood Pressure", "HbA1c"])]
        )
        # phs000001 has SBP, phs000002 has HbA1c, phs000003 has SBP
        assert _ids(result) == {"phs000001", "phs000002", "phs000003"}

    def test_or_platform(self, store: DuckDBStore) -> None:
        """Two platforms — studies on either platform match."""
        result = store.query_studies(
            [(Facet.PLATFORM, ["BDC", "CRDC"])]
        )
        # phs000001 BDC, phs000002 BDC, phs000004 AnVIL+BDC, phs000005 CRDC
        assert _ids(result) == {"phs000001", "phs000002", "phs000004", "phs000005"}

    def test_or_focus(self, store: DuckDBStore) -> None:
        """Two focus values — studies with either focus match."""
        result = store.query_studies(
            [(Facet.FOCUS, ["Cardiovascular", "Diabetes"])]
        )
        assert _ids(result) == {"phs000001", "phs000002", "phs000003"}

    def test_or_data_type(self, store: DuckDBStore) -> None:
        """Two data types — studies with either type match."""
        result = store.query_studies(
            [(Facet.DATA_TYPE, ["WGS", "RNA-Seq"])]
        )
        # phs000001 WGS, phs000002 WGS+WES, phs000004 RNA-Seq, phs000005 WGS
        assert _ids(result) == {"phs000001", "phs000002", "phs000004", "phs000005"}


# ---------------------------------------------------------------------------
# AND within a single facet (same facet, separate constraints)
# ---------------------------------------------------------------------------


class TestANDWithinFacet:
    """AND within a facet: studies must have ALL requested values.

    Each value is passed as a separate constraint tuple so they are AND-ed.
    """

    def test_and_measurements_both_present(self, store: DuckDBStore) -> None:
        """Studies with BOTH SBP AND BMI."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
            (Facet.MEASUREMENT, ["BMI"]),
        ])
        # phs000001: SBP + BMI yes
        # phs000002: BMI only
        # phs000003: SBP only
        assert _ids(result) == {"phs000001"}

    def test_and_measurements_no_study_has_both(self, store: DuckDBStore) -> None:
        """No study has BOTH HbA1c AND Heart Rate."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["HbA1c"]),
            (Facet.MEASUREMENT, ["Heart Rate"]),
        ])
        assert result == []

    def test_and_measurements_three_values(self, store: DuckDBStore) -> None:
        """Studies with SBP AND DBP AND BMI — only phs000001."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
            (Facet.MEASUREMENT, ["Diastolic Blood Pressure"]),
            (Facet.MEASUREMENT, ["BMI"]),
        ])
        assert _ids(result) == {"phs000001"}

    def test_and_data_types(self, store: DuckDBStore) -> None:
        """Studies with BOTH WGS AND WES — only phs000002."""
        result = store.query_studies([
            (Facet.DATA_TYPE, ["WGS"]),
            (Facet.DATA_TYPE, ["WES"]),
        ])
        assert _ids(result) == {"phs000002"}

    def test_and_platforms(self, store: DuckDBStore) -> None:
        """Studies on BOTH AnVIL AND BDC — only phs000004."""
        result = store.query_studies([
            (Facet.PLATFORM, ["AnVIL"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        assert _ids(result) == {"phs000004"}

    def test_or_vs_and_within_measurement(self, store: DuckDBStore) -> None:
        """Demonstrate that one tuple OR-es values within a facet,
        while separate tuples AND them."""
        or_result = store.query_studies(
            [(Facet.MEASUREMENT, ["Systolic Blood Pressure", "BMI"])]
        )
        and_result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
            (Facet.MEASUREMENT, ["BMI"]),
        ])
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
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        # phs000001 has SBP + BDC; phs000003 has SBP but is AnVIL only
        assert _ids(result) == {"phs000001"}

    def test_focus_and_data_type(self, store: DuckDBStore) -> None:
        """Cancer focus AND WGS — only phs000005."""
        result = store.query_studies([
            (Facet.FOCUS, ["Cancer"]),
            (Facet.DATA_TYPE, ["WGS"]),
        ])
        # phs000004 is Cancer but RNA-Seq; phs000005 is Cancer + WGS
        assert _ids(result) == {"phs000005"}

    def test_three_facets(self, store: DuckDBStore) -> None:
        """Measurement AND platform AND focus — narrow intersection."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["BMI"]),
            (Facet.PLATFORM, ["BDC"]),
            (Facet.FOCUS, ["Cardiovascular"]),
        ])
        # phs000001: BMI + BDC + Cardiovascular yes
        # phs000002: BMI + BDC + Diabetes no (wrong focus)
        assert _ids(result) == {"phs000001"}

    def test_and_empty_intersection(self, store: DuckDBStore) -> None:
        """No study satisfies all constraints — empty result."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Tumor Size"]),
            (Facet.PLATFORM, ["BDC"]),
            (Facet.FOCUS, ["Diabetes"]),
        ])
        assert result == []


# ---------------------------------------------------------------------------
# OR within + AND between (combined)
# ---------------------------------------------------------------------------


class TestORWithinANDBetween:
    """OR within facets combined with AND between facets."""

    def test_or_measurements_and_platform(self, store: DuckDBStore) -> None:
        """(SBP OR HbA1c) AND BDC."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure", "HbA1c"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        # phs000001: SBP + BDC yes
        # phs000002: HbA1c + BDC yes
        # phs000003: SBP + AnVIL no
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_or_platforms_and_focus(self, store: DuckDBStore) -> None:
        """Cancer AND (BDC OR CRDC)."""
        result = store.query_studies([
            (Facet.FOCUS, ["Cancer"]),
            (Facet.PLATFORM, ["BDC", "CRDC"]),
        ])
        # phs000004: Cancer + BDC yes
        # phs000005: Cancer + CRDC yes
        assert _ids(result) == {"phs000004", "phs000005"}

    def test_or_both_facets(self, store: DuckDBStore) -> None:
        """(SBP OR BMI) AND (BDC OR AnVIL)."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["Systolic Blood Pressure", "BMI"]),
            (Facet.PLATFORM, ["BDC", "AnVIL"]),
        ])
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
            include=[(Facet.MEASUREMENT, ["Systolic Blood Pressure"])],
            exclude=[(Facet.PLATFORM, ["AnVIL"])],
        )
        # phs000001: SBP + BDC yes (not AnVIL)
        # phs000003: SBP + AnVIL no (excluded)
        assert _ids(result) == {"phs000001"}

    def test_exclude_focus(self, store: DuckDBStore) -> None:
        """BDC studies NOT Cancer."""
        result = store.query_studies(
            include=[(Facet.PLATFORM, ["BDC"])],
            exclude=[(Facet.FOCUS, ["Cancer"])],
        )
        # BDC: phs000001, phs000002, phs000004
        # phs000004 is Cancer -> excluded
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_exclude_measurement(self, store: DuckDBStore) -> None:
        """Cancer studies NOT with Tumor Size."""
        result = store.query_studies(
            include=[(Facet.FOCUS, ["Cancer"])],
            exclude=[(Facet.MEASUREMENT, ["Tumor Size"])],
        )
        # Cancer: phs000004, phs000005 — both have Tumor Size -> all excluded
        assert result == []

    def test_exclude_no_overlap(self, store: DuckDBStore) -> None:
        """Exclude that doesn't overlap with includes — no effect."""
        result = store.query_studies(
            include=[(Facet.FOCUS, ["Diabetes"])],
            exclude=[(Facet.PLATFORM, ["CRDC"])],
        )
        # Diabetes: phs000002 (BDC) — CRDC exclude doesn't touch it
        assert _ids(result) == {"phs000002"}

    def test_exclude_with_and(self, store: DuckDBStore) -> None:
        """(BMI AND BDC) NOT Cardiovascular."""
        result = store.query_studies(
            include=[
                (Facet.MEASUREMENT, ["BMI"]),
                (Facet.PLATFORM, ["BDC"]),
            ],
            exclude=[(Facet.FOCUS, ["Cardiovascular"])],
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
            [(Facet.MEASUREMENT, ["systolic blood pressure"])]
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_measurement_uppercase(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            [(Facet.MEASUREMENT, ["SYSTOLIC BLOOD PRESSURE"])]
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_measurement_mixed_case(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            [(Facet.MEASUREMENT, ["sYsToLiC bLoOd PrEsSuRe"])]
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_platform_lowercase(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            [(Facet.PLATFORM, ["bdc"])]
        )
        assert _ids(result) == {"phs000001", "phs000002", "phs000004"}

    def test_focus_mixed_case(self, store: DuckDBStore) -> None:
        result = store.query_studies(
            [(Facet.FOCUS, ["cAnCeR"])]
        )
        assert _ids(result) == {"phs000004", "phs000005"}

    def test_case_insensitive_and(self, store: DuckDBStore) -> None:
        """Case insensitivity works across AND-ed facets."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["bmi"]),
            (Facet.PLATFORM, ["anvil"]),
        ])
        # phs000001: BMI + BDC, phs000002: BMI + BDC — neither on AnVIL
        assert result == []

    def test_case_insensitive_or_and_combined(self, store: DuckDBStore) -> None:
        """Mixed case in OR values with AND between facets."""
        result = store.query_studies([
            (Facet.MEASUREMENT, ["SYSTOLIC BLOOD PRESSURE", "hba1c"]),
            (Facet.PLATFORM, ["bdc"]),
        ])
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_case_insensitive_exclude(self, store: DuckDBStore) -> None:
        """Exclude matching is also case-insensitive."""
        result = store.query_studies(
            include=[(Facet.PLATFORM, ["bdc"])],
            exclude=[(Facet.FOCUS, ["CANCER"])],
        )
        assert _ids(result) == {"phs000001", "phs000002"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Empty inputs, no matches, single study results."""

    def test_empty_facet_values(self, store: DuckDBStore) -> None:
        """Empty values list for a facet — should return nothing."""
        result = store.query_studies([(Facet.MEASUREMENT, [])])
        assert result == []

    def test_no_matching_value(self, store: DuckDBStore) -> None:
        """Value that doesn't exist in the store."""
        result = store.query_studies(
            [(Facet.MEASUREMENT, ["Nonexistent Concept"])]
        )
        assert result == []

    def test_empty_list(self, store: DuckDBStore) -> None:
        """Empty include list."""
        result = store.query_studies([])
        assert result == []

    def test_single_study_match(self, store: DuckDBStore) -> None:
        """Only one study has Fasting Glucose."""
        result = store.query_studies(
            [(Facet.MEASUREMENT, ["Fasting Glucose"])]
        )
        assert _ids(result) == {"phs000002"}

    def test_results_sorted_by_id(self, store: DuckDBStore) -> None:
        """Results should be sorted by dbGapId."""
        result = store.query_studies(
            [(Facet.PLATFORM, ["BDC"])]
        )
        ids = [s["dbGapId"] for s in result]
        assert ids == sorted(ids)

    def test_study_count(self, store: DuckDBStore) -> None:
        """study_count reflects the number of loaded studies."""
        assert store.study_count == 5

    def test_returned_study_has_full_data(self, store: DuckDBStore) -> None:
        """Returned study dicts contain the original fields."""
        result = store.query_studies(
            [(Facet.MEASUREMENT, ["Fasting Glucose"])]
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
            [(Facet.MEASUREMENT, ["Systolic Blood Pressure"])]
        )
        assert _ids(result) == {"phs000001", "phs000003"}

    def test_loaded_store_supports_and(self, store: DuckDBStore, tmp_path) -> None:
        """AND between facets works on a loaded store."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.query_studies([
            (Facet.MEASUREMENT, ["BMI"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_loaded_store_supports_exclude(self, store: DuckDBStore, tmp_path) -> None:
        """Exclude logic works on a loaded store."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.query_studies(
            include=[(Facet.PLATFORM, ["BDC"])],
            exclude=[(Facet.FOCUS, ["Cancer"])],
        )
        assert _ids(result) == {"phs000001", "phs000002"}

    def test_loaded_store_supports_same_facet_and(
        self, store: DuckDBStore, tmp_path
    ) -> None:
        """Same-facet AND works on a loaded store."""
        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)
        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.query_studies([
            (Facet.PLATFORM, ["AnVIL"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        assert _ids(result) == {"phs000004"}

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


# ---------------------------------------------------------------------------
# Demographics: normalization
# ---------------------------------------------------------------------------


class TestDemographicNormalization:
    """Label normalization via _normalize_categories."""

    def test_verbatim_female_normalizes(self) -> None:
        """Verbatim 'FEMALE' → canonical 'Female'."""
        mappings = _load_demographic_mappings()
        cats = [{"count": 50, "label": "FEMALE"}]
        result = _normalize_categories(cats, mappings["sex"], "Other/Unknown")
        assert len(result) == 1
        assert result[0]["label"] == "Female"
        assert result[0]["count"] == 50

    def test_multiple_verbatim_labels_summed(self) -> None:
        """Multiple verbatim labels mapping to same canonical have counts summed."""
        mappings = _load_demographic_mappings()
        cats = [
            {"count": 30, "label": "Female"},
            {"count": 20, "label": "female"},
            {"count": 10, "label": "FEMALE"},
        ]
        result = _normalize_categories(cats, mappings["sex"], "Other/Unknown")
        female = [c for c in result if c["label"] == "Female"]
        assert len(female) == 1
        assert female[0]["count"] == 60

    def test_unmapped_race_falls_back_to_other(self) -> None:
        """An unmapped race/ethnicity label maps to 'Other'."""
        mappings = _load_demographic_mappings()
        cats = [{"count": 5, "label": "Martian"}]
        result = _normalize_categories(cats, mappings["raceEthnicity"], "Other")
        assert len(result) == 1
        assert result[0]["label"] == "Other"
        assert result[0]["count"] == 5

    def test_black_normalizes_to_canonical(self) -> None:
        """Verbatim 'Black' → 'Black or African American'."""
        mappings = _load_demographic_mappings()
        cats = [{"count": 100, "label": "Black"}]
        result = _normalize_categories(cats, mappings["raceEthnicity"], "Other")
        assert result[0]["label"] == "Black or African American"

    def test_results_sorted_by_count_descending(self) -> None:
        """Normalized results are sorted by count descending."""
        mappings = _load_demographic_mappings()
        cats = [
            {"count": 10, "label": "Male"},
            {"count": 50, "label": "Female"},
            {"count": 5, "label": "Unknown"},
        ]
        result = _normalize_categories(cats, mappings["sex"], "Other/Unknown")
        counts = [c["count"] for c in result]
        assert counts == sorted(counts, reverse=True)

    def test_zero_count_categories_excluded(self) -> None:
        """Categories with count=0 are filtered out to avoid false positives."""
        from concept_search.index import _load_demographic_profiles

        data = {
            "studies": {
                "phs999999": {
                    "sex": {
                        "n": 100,
                        "categories": [
                            {"label": "Male", "count": 100},
                            {"label": "Female", "count": 0},
                        ],
                    },
                },
            },
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        mappings = _load_demographic_mappings()
        with unittest.mock.patch(
            "concept_search.index._resolve_demographics_path",
            return_value=Path(tmp_path),
        ):
            demo_dict, eav_rows = _load_demographic_profiles(mappings)

        os.unlink(tmp_path)

        # Female with count=0 should be excluded from both
        study_demo = demo_dict["phs999999"]["sex"]
        labels = [c["label"] for c in study_demo["categories"]]
        assert "Female" not in labels
        assert "Male" in labels

        # No EAV row for Female
        eav_labels = [v for _, _, v, _ in eav_rows]
        assert "Female" not in eav_labels
        assert "Male" in eav_labels


# ---------------------------------------------------------------------------
# Demographics: EAV in DuckDB store
# ---------------------------------------------------------------------------


def _build_store_with_demographics() -> DuckDBStore:
    """Build a store with demographic facet values for testing."""
    studies = [
        {
            "dbGapId": "phs000010",
            "title": "Study 10",
            "platforms": ["BDC"],
            "demographics": {
                "sex": {
                    "categories": [
                        {"count": 60, "label": "Female", "percent": 60.0},
                        {"count": 40, "label": "Male", "percent": 40.0},
                    ],
                    "n": 100,
                },
            },
        },
        {
            "dbGapId": "phs000011",
            "title": "Study 11",
            "platforms": ["AnVIL"],
            "demographics": {
                "sex": {
                    "categories": [
                        {"count": 80, "label": "Male", "percent": 80.0},
                        {"count": 20, "label": "Female", "percent": 20.0},
                    ],
                    "n": 100,
                },
                "raceEthnicity": {
                    "categories": [
                        {"count": 70, "label": "White", "percent": 70.0},
                        {
                            "count": 30,
                            "label": "Black or African American",
                            "percent": 30.0,
                        },
                    ],
                    "n": 100,
                },
            },
        },
        {
            "dbGapId": "phs000012",
            "title": "Study 12",
            "platforms": ["BDC"],
        },
    ]

    store = DuckDBStore.create_empty()
    for study in studies:
        sid = study["dbGapId"]
        store.load_study(sid, study)
        # Platform facet
        for p in study.get("platforms", []):
            store.load_facet_value(sid, Facet.PLATFORM, p)

    # Demographic EAV rows
    demo_rows = [
        ("phs000010", "sex", "Female", "female"),
        ("phs000010", "sex", "Male", "male"),
        ("phs000011", "sex", "Male", "male"),
        ("phs000011", "sex", "Female", "female"),
        ("phs000011", "raceEthnicity", "White", "white"),
        ("phs000011", "raceEthnicity", "Black or African American", "black or african american"),
    ]
    store.load_facet_values_batch(demo_rows)
    store.finalize()
    return store


class TestDemographicSearch:
    """Demographic facet values are searchable in DuckDB."""

    @pytest.fixture
    def demo_store(self) -> DuckDBStore:
        return _build_store_with_demographics()

    def test_sex_female_returns_correct_studies(self, demo_store: DuckDBStore) -> None:
        """Searching sex=Female returns studies with female participants."""
        result = demo_store.query_studies([(Facet.SEX, ["Female"])])
        assert _ids(result) == {"phs000010", "phs000011"}

    def test_race_ethnicity_search(self, demo_store: DuckDBStore) -> None:
        """Searching raceEthnicity returns matching studies."""
        result = demo_store.query_studies(
            [(Facet.RACE_ETHNICITY, ["Black or African American"])]
        )
        assert _ids(result) == {"phs000011"}

    def test_sex_and_platform_combined(self, demo_store: DuckDBStore) -> None:
        """Demographic AND platform facets work together."""
        result = demo_store.query_studies([
            (Facet.SEX, ["Female"]),
            (Facet.PLATFORM, ["BDC"]),
        ])
        # phs000010: Female + BDC ✓
        # phs000011: Female + AnVIL ✗
        assert _ids(result) == {"phs000010"}

    def test_study_without_demographics_excluded(self, demo_store: DuckDBStore) -> None:
        """Studies without demographics don't appear in demographic searches."""
        result = demo_store.query_studies([(Facet.SEX, ["Male"])])
        assert "phs000012" not in _ids(result)

    def test_demographics_in_raw_json_roundtrip(self, demo_store: DuckDBStore) -> None:
        """Demographics stored in raw_json survive DuckDB roundtrip."""
        result = demo_store.query_studies([(Facet.PLATFORM, ["BDC"])])
        study_10 = next(s for s in result if s["dbGapId"] == "phs000010")
        assert "demographics" in study_10
        assert study_10["demographics"]["sex"]["n"] == 100

        study_12 = next(s for s in result if s["dbGapId"] == "phs000012")
        assert "demographics" not in study_12


# ---------------------------------------------------------------------------
# Demographics: API response building
# ---------------------------------------------------------------------------


class TestBuildStudySummary:
    """_build_study_summary produces correct StudyDemographics."""

    def test_study_with_demographics(self) -> None:
        """StudySummary includes demographics when present."""
        study = {
            "consentCodes": [],
            "dataTypes": [],
            "dbGapId": "phs000099",
            "demographics": {
                "sex": {
                    "categories": [
                        {"count": 60, "label": "Female", "percent": 60.0},
                        {"count": 40, "label": "Male", "percent": 40.0},
                    ],
                    "n": 100,
                },
            },
            "focus": None,
            "participantCount": 100,
            "platforms": ["BDC"],
            "studyDesigns": [],
            "title": "Test Study",
        }
        summary = _build_study_summary(study)
        assert summary.demographics is not None
        assert summary.demographics.sex is not None
        assert summary.demographics.sex.n == 100
        assert len(summary.demographics.sex.categories) == 2
        assert summary.demographics.sex.categories[0].label == "Female"
        assert summary.demographics.sex.categories[0].percent == 60.0
        assert summary.demographics.race_ethnicity is None
        assert summary.demographics.computed_ancestry is None

    def test_study_without_demographics(self) -> None:
        """StudySummary has demographics=None when no data."""
        study = {
            "consentCodes": [],
            "dataTypes": [],
            "dbGapId": "phs000100",
            "focus": None,
            "participantCount": 50,
            "platforms": ["AnVIL"],
            "studyDesigns": [],
            "title": "No Demo Study",
        }
        summary = _build_study_summary(study)
        assert summary.demographics is None

    def test_percent_computation(self) -> None:
        """Percent values are correct in the response."""
        study = {
            "consentCodes": [],
            "dataTypes": [],
            "dbGapId": "phs000101",
            "demographics": {
                "sex": {
                    "categories": [
                        {"count": 60, "label": "Male", "percent": 60.0},
                        {"count": 40, "label": "Female", "percent": 40.0},
                    ],
                    "n": 100,
                },
            },
            "focus": None,
            "participantCount": 100,
            "platforms": [],
            "studyDesigns": [],
            "title": "Pct Test",
        }
        summary = _build_study_summary(study)
        cats = summary.demographics.sex.categories
        assert cats[0].percent == 60.0
        assert cats[1].percent == 40.0

    def test_zero_n_no_division_error(self) -> None:
        """n=0 produces percent=0.0 without ZeroDivisionError."""
        # This tests the normalization path where percent is pre-computed
        study = {
            "consentCodes": [],
            "dataTypes": [],
            "dbGapId": "phs000102",
            "demographics": {
                "sex": {
                    "categories": [
                        {"count": 0, "label": "Male", "percent": 0.0},
                    ],
                    "n": 0,
                },
            },
            "focus": None,
            "participantCount": 0,
            "platforms": [],
            "studyDesigns": [],
            "title": "Zero N",
        }
        summary = _build_study_summary(study)
        assert summary.demographics.sex.categories[0].percent == 0.0

    def test_all_three_dimensions(self) -> None:
        """StudySummary with sex, raceEthnicity, and computedAncestry."""
        study = {
            "consentCodes": [],
            "dataTypes": [],
            "dbGapId": "phs000103",
            "demographics": {
                "computedAncestry": {
                    "categories": [
                        {"count": 80, "label": "European", "percent": 80.0},
                        {"count": 20, "label": "African American", "percent": 20.0},
                    ],
                    "n": 100,
                },
                "raceEthnicity": {
                    "categories": [
                        {"count": 70, "label": "White", "percent": 70.0},
                    ],
                    "n": 100,
                },
                "sex": {
                    "categories": [
                        {"count": 50, "label": "Female", "percent": 50.0},
                    ],
                    "n": 100,
                },
            },
            "focus": None,
            "participantCount": 100,
            "platforms": [],
            "studyDesigns": [],
            "title": "Full Demo",
        }
        summary = _build_study_summary(study)
        assert summary.demographics.sex is not None
        assert summary.demographics.race_ethnicity is not None
        assert summary.demographics.computed_ancestry is not None
        assert summary.demographics.computed_ancestry.categories[0].label == "European"
