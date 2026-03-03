"""Tests for the MCP catalog discovery server.

Calls each tool function directly with a synthetic ConceptIndex
backed by an in-memory DuckDB store — no real catalog data or MCP
transport needed.
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest

from concept_search.index import ConceptIndex
from concept_search.models import ConceptMatch, Facet
from concept_search.store import DuckDBStore


# ---------------------------------------------------------------------------
# Helpers — build synthetic store + index
# ---------------------------------------------------------------------------


def _make_study(
    dbgap_id: str,
    *,
    platforms: list[str] | None = None,
    focus: str | None = None,
    data_types: list[str] | None = None,
    consent_codes: list[str] | None = None,
    study_designs: list[str] | None = None,
    participant_count: int = 100,
) -> dict:
    study: dict = {
        "dbGapId": dbgap_id,
        "participantCount": participant_count,
        "title": f"Study {dbgap_id}",
    }
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


STUDIES = [
    _make_study(
        "phs000001",
        platforms=["BDC"],
        focus="Cardiovascular Diseases",
        data_types=["WGS"],
        consent_codes=["HMB"],
        study_designs=["Prospective Longitudinal Cohort"],
        participant_count=5000,
    ),
    _make_study(
        "phs000002",
        platforms=["BDC"],
        focus="Diabetes Mellitus, Type 2",
        data_types=["WGS", "WES"],
        consent_codes=["GRU"],
        study_designs=["Case-Control"],
        participant_count=3000,
    ),
    _make_study(
        "phs000003",
        platforms=["AnVIL"],
        focus="Cardiovascular Diseases",
        data_types=["WES"],
        consent_codes=["HMB-NPU"],
        study_designs=["Prospective Longitudinal Cohort"],
        participant_count=1000,
    ),
]

STUDY_CONCEPTS = {
    "phs000001": {"ncpi:biomarkers", "ncpi:bp_systolic", "ncpi:bp_diastolic", "ncpi:bmi"},
    "phs000002": {"ncpi:biomarkers", "ncpi:bmi", "ncpi:hba1c", "ncpi:fasting_glucose"},
    "phs000003": {"ncpi:biomarkers", "ncpi:bp_systolic", "ncpi:heart_rate"},
}

# ISA hierarchy: ncpi:biomarkers -> ncpi:bp_systolic, ncpi:bp_diastolic, etc.
ISA = {
    "ncpi:biomarkers": [
        "ncpi:bp_systolic",
        "ncpi:bp_diastolic",
        "ncpi:bmi",
        "ncpi:hba1c",
        "ncpi:fasting_glucose",
        "ncpi:heart_rate",
    ],
}

CATEGORIES = [
    {"concept_id": "ncpi:biomarkers", "description": "Biomarker measurements", "name": "Biomarkers"},
    {"concept_id": "ncpi:imaging", "description": "Imaging studies", "name": "Imaging"},
]


def _build_store() -> DuckDBStore:
    """Build a DuckDBStore from synthetic data."""
    store = DuckDBStore.create_empty()

    facet_field_map = {
        Facet.CONSENT_CODE: "consentCodes",
        Facet.DATA_TYPE: "dataTypes",
        Facet.FOCUS: "focus",
        Facet.PLATFORM: "platforms",
        Facet.STUDY_DESIGN: "studyDesigns",
    }

    for study in STUDIES:
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

    for sid, concepts in STUDY_CONCEPTS.items():
        for concept in concepts:
            store.load_facet_value(sid, Facet.MEASUREMENT, concept)

    # Load variables
    rows = [
        ("ncpi:bp_systolic", "ncpi:bp_systolic", "",
         json.dumps(["ncpi:bp_systolic", "ncpi:biomarkers"]),
         "ds1", "Systolic blood pressure", "phv001", "phs000001", "exam1", "SBP"),
        ("ncpi:bp_diastolic", "ncpi:bp_diastolic", "",
         json.dumps(["ncpi:bp_diastolic", "ncpi:biomarkers"]),
         "ds1", "Diastolic blood pressure", "phv002", "phs000001", "exam1", "DBP"),
        ("ncpi:hba1c", "ncpi:hba1c", "",
         json.dumps(["ncpi:hba1c", "ncpi:biomarkers"]),
         "ds2", "Hemoglobin A1c", "phv003", "phs000002", "lab1", "HBA1C"),
    ]
    store.load_variables_batch(rows)
    store.finalize()
    return store


def _build_index(store: DuckDBStore) -> ConceptIndex:
    """Build a ConceptIndex from a synthetic store without loading files."""
    index = ConceptIndex.__new__(ConceptIndex)
    index.store = store
    index._isa = ISA
    index._reverse_isa = {}
    for parent, children in ISA.items():
        for child in children:
            index._reverse_isa[child] = parent

    # _isa_children: parent -> list of direct children
    index._isa_children = ISA

    # _concept_descriptions: concept_id -> {name, description}
    index._concept_descriptions = {
        "ncpi:bp_systolic": {"name": "Systolic Blood Pressure", "description": "Systolic BP measurement"},
        "ncpi:bp_diastolic": {"name": "Diastolic Blood Pressure", "description": "Diastolic BP measurement"},
        "ncpi:bmi": {"name": "BMI", "description": "Body mass index"},
        "ncpi:hba1c": {"name": "HbA1c", "description": "Glycosylated hemoglobin"},
        "ncpi:fasting_glucose": {"name": "Fasting Glucose", "description": "Fasting glucose level"},
        "ncpi:heart_rate": {"name": "Heart Rate", "description": "Heart rate measurement"},
    }

    # Build the internal index from store facet values — initialize all facets
    index._index = {f: {} for f in Facet}
    for facet_str, value, count in store.get_facet_value_counts():
        facet = Facet(facet_str)
        index._index[facet][value.lower()] = ConceptMatch(
            facet=facet,
            study_count=count,
            value=value,
        )

    return index


# ---------------------------------------------------------------------------
# Fixture: patch the server's _get_index to use synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def _patch_index(tmp_path: Path):
    """Patch mcp_catalog.server._get_index and categories path."""
    store = _build_store()
    index = _build_index(store)

    # Write synthetic categories file
    cat_path = tmp_path / "ncpi-categories.json"
    cat_path.write_text(json.dumps(CATEGORIES))

    with (
        unittest.mock.patch("mcp_catalog.server._get_index", return_value=index),
        unittest.mock.patch("mcp_catalog.server._CATEGORIES_PATH", cat_path),
    ):
        yield index


# ---------------------------------------------------------------------------
# Tool tests
# ---------------------------------------------------------------------------


class TestBrowseConcepts:
    """browse_concepts returns top-level categories with study counts."""

    @pytest.mark.usefixtures("_patch_index")
    def test_returns_categories(self) -> None:
        from mcp_catalog.server import browse_concepts

        result = browse_concepts()
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert "Biomarkers" in names
        assert "Imaging" in names

    @pytest.mark.usefixtures("_patch_index")
    def test_biomarkers_has_study_count(self) -> None:
        from mcp_catalog.server import browse_concepts

        result = browse_concepts()
        biomarkers = next(r for r in result if r["name"] == "Biomarkers")
        # All 3 studies have at least one biomarker concept
        assert biomarkers["study_count"] > 0

    @pytest.mark.usefixtures("_patch_index")
    def test_imaging_has_zero_studies(self) -> None:
        from mcp_catalog.server import browse_concepts

        result = browse_concepts()
        imaging = next(r for r in result if r["name"] == "Imaging")
        assert imaging["study_count"] == 0

    @pytest.mark.usefixtures("_patch_index")
    def test_sorted_by_study_count_descending(self) -> None:
        from mcp_catalog.server import browse_concepts

        result = browse_concepts()
        counts = [r["study_count"] for r in result]
        assert counts == sorted(counts, reverse=True)


class TestGetConceptChildren:
    """get_concept_children drills into a parent concept."""

    @pytest.mark.usefixtures("_patch_index")
    def test_returns_children(self) -> None:
        from mcp_catalog.server import get_concept_children

        result = get_concept_children("ncpi:biomarkers")
        assert isinstance(result, list)
        child_ids = {r["concept_id"] for r in result}
        assert "ncpi:bp_systolic" in child_ids
        assert "ncpi:hba1c" in child_ids

    @pytest.mark.usefixtures("_patch_index")
    def test_nonexistent_parent_returns_empty(self) -> None:
        from mcp_catalog.server import get_concept_children

        result = get_concept_children("ncpi:nonexistent")
        assert result == []


class TestSearchConcepts:
    """search_concepts finds concepts by keyword."""

    @pytest.mark.usefixtures("_patch_index")
    def test_search_by_keyword(self) -> None:
        from mcp_catalog.server import search_concepts

        result = search_concepts("systolic")
        assert len(result) > 0
        values = {r["value"] for r in result}
        assert "ncpi:bp_systolic" in values

    @pytest.mark.usefixtures("_patch_index")
    def test_search_with_facet_filter(self) -> None:
        from mcp_catalog.server import search_concepts

        result = search_concepts("BDC", facet="platform")
        assert len(result) > 0
        assert all(r["facet"] == "platform" for r in result)

    @pytest.mark.usefixtures("_patch_index")
    def test_search_no_match(self) -> None:
        from mcp_catalog.server import search_concepts

        result = search_concepts("xyzzyzzyxnotarealterm")
        assert result == []

    @pytest.mark.usefixtures("_patch_index")
    def test_result_shape(self) -> None:
        from mcp_catalog.server import search_concepts

        result = search_concepts("bmi")
        assert len(result) > 0
        item = result[0]
        assert "facet" in item
        assert "study_count" in item
        assert "value" in item


class TestSearchStudies:
    """search_studies filters studies by faceted criteria."""

    @pytest.mark.usefixtures("_patch_index")
    def test_filter_by_platform(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(platform=["BDC"])
        assert result["total"] == 2
        ids = {s["dbGapId"] for s in result["studies"]}
        assert ids == {"phs000001", "phs000002"}

    @pytest.mark.usefixtures("_patch_index")
    def test_filter_by_data_type(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(data_type=["WGS"])
        ids = {s["dbGapId"] for s in result["studies"]}
        assert "phs000001" in ids
        assert "phs000002" in ids

    @pytest.mark.usefixtures("_patch_index")
    def test_filter_by_measurement(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(measurement=["ncpi:hba1c"])
        assert result["total"] == 1
        assert result["studies"][0]["dbGapId"] == "phs000002"

    @pytest.mark.usefixtures("_patch_index")
    def test_and_across_facets(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(
            platform=["BDC"],
            focus=["Cardiovascular Diseases"],
        )
        assert result["total"] == 1
        assert result["studies"][0]["dbGapId"] == "phs000001"

    @pytest.mark.usefixtures("_patch_index")
    def test_or_within_facet(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(
            focus=["Cardiovascular Diseases", "Diabetes Mellitus, Type 2"]
        )
        assert result["total"] == 3

    @pytest.mark.usefixtures("_patch_index")
    def test_no_filters_returns_error(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies()
        assert "error" in result
        assert result["total"] == 0

    @pytest.mark.usefixtures("_patch_index")
    def test_study_summary_shape(self) -> None:
        from mcp_catalog.server import search_studies

        result = search_studies(platform=["BDC"])
        study = result["studies"][0]
        assert "dbGapId" in study
        assert "title" in study
        assert "platforms" in study
        assert "dataTypes" in study
        assert "consentCodes" in study
        assert "participantCount" in study
        assert "focus" in study


class TestSearchVariables:
    """search_variables finds dbGaP variables by concept."""

    @pytest.mark.usefixtures("_patch_index")
    def test_by_concept(self) -> None:
        from mcp_catalog.server import search_variables

        result = search_variables(concepts=["ncpi:bp_systolic"])
        assert result["total"] == 1
        assert result["variables"][0]["variableName"] == "SBP"

    @pytest.mark.usefixtures("_patch_index")
    def test_by_concept_and_study(self) -> None:
        from mcp_catalog.server import search_variables

        result = search_variables(
            concepts=["ncpi:hba1c"],
            study_ids=["phs000002"],
        )
        assert result["total"] == 1
        assert result["variables"][0]["variableName"] == "HBA1C"

    @pytest.mark.usefixtures("_patch_index")
    def test_concept_study_mismatch(self) -> None:
        from mcp_catalog.server import search_variables

        result = search_variables(
            concepts=["ncpi:hba1c"],
            study_ids=["phs000001"],
        )
        assert result["total"] == 0

    @pytest.mark.usefixtures("_patch_index")
    def test_limit(self) -> None:
        from mcp_catalog.server import search_variables

        result = search_variables(
            concepts=["ncpi:bp_systolic", "ncpi:bp_diastolic"],
            limit=1,
        )
        assert len(result["variables"]) <= 1

    @pytest.mark.usefixtures("_patch_index")
    def test_variable_shape(self) -> None:
        from mcp_catalog.server import search_variables

        result = search_variables(concepts=["ncpi:bp_systolic"])
        var = result["variables"][0]
        assert "concept" in var
        assert "description" in var
        assert "phvId" in var
        assert "studyId" in var
        assert "variableName" in var


class TestGetStudy:
    """get_study returns full study details."""

    @pytest.mark.usefixtures("_patch_index")
    def test_existing_study(self) -> None:
        from mcp_catalog.server import get_study

        result = get_study("phs000001")
        assert result is not None
        assert result["dbGapId"] == "phs000001"
        assert result["title"] == "Study phs000001"

    @pytest.mark.usefixtures("_patch_index")
    def test_returns_full_record(self) -> None:
        from mcp_catalog.server import get_study

        result = get_study("phs000002")
        assert result["dbGapId"] == "phs000002"
        assert result["dataTypes"] == ["WGS", "WES"]
        assert result["consentCodes"] == ["GRU"]
        assert result["participantCount"] == 3000

    @pytest.mark.usefixtures("_patch_index")
    def test_nonexistent_returns_none(self) -> None:
        from mcp_catalog.server import get_study

        result = get_study("phs999999")
        assert result is None


class TestListFacetValues:
    """list_facet_values lists all values for a facet."""

    @pytest.mark.usefixtures("_patch_index")
    def test_platform_values(self) -> None:
        from mcp_catalog.server import list_facet_values

        result = list_facet_values("platform")
        assert isinstance(result, list)
        values = {r["value"] for r in result}
        assert "BDC" in values
        assert "AnVIL" in values

    @pytest.mark.usefixtures("_patch_index")
    def test_result_has_study_count(self) -> None:
        from mcp_catalog.server import list_facet_values

        result = list_facet_values("platform")
        bdc = next(r for r in result if r["value"] == "BDC")
        assert bdc["study_count"] == 2

    @pytest.mark.usefixtures("_patch_index")
    def test_measurement_values(self) -> None:
        from mcp_catalog.server import list_facet_values

        result = list_facet_values("measurement")
        values = {r["value"] for r in result}
        assert "ncpi:bp_systolic" in values
        assert "ncpi:hba1c" in values


class TestComputeConsentEligibility:
    """compute_consent_eligibility returns eligible consent codes."""

    @pytest.mark.usefixtures("_patch_index")
    def test_general_purpose(self) -> None:
        from mcp_catalog.server import compute_consent_eligibility

        result = compute_consent_eligibility(purpose="general")
        assert "eligible_codes" in result
        assert "total_eligible" in result
        assert "GRU" in result["eligible_codes"]

    @pytest.mark.usefixtures("_patch_index")
    def test_nonprofit_false_excludes_npu(self) -> None:
        from mcp_catalog.server import compute_consent_eligibility

        result = compute_consent_eligibility(
            purpose="general", is_nonprofit=False
        )
        for code in result["eligible_codes"]:
            assert "NPU" not in code

    @pytest.mark.usefixtures("_patch_index")
    def test_explicit_code_prefix(self) -> None:
        from mcp_catalog.server import compute_consent_eligibility

        result = compute_consent_eligibility(explicit_code="HMB")
        assert any(c.startswith("HMB") for c in result["eligible_codes"])


class TestGetCatalogStats:
    """get_catalog_stats returns summary statistics."""

    @pytest.mark.usefixtures("_patch_index")
    def test_returns_stats(self) -> None:
        from mcp_catalog.server import get_catalog_stats

        result = get_catalog_stats()
        assert "facet_value_counts" in result
        assert "study_count" in result

    @pytest.mark.usefixtures("_patch_index")
    def test_study_count(self) -> None:
        from mcp_catalog.server import get_catalog_stats

        result = get_catalog_stats()
        assert result["study_count"] == 3

    @pytest.mark.usefixtures("_patch_index")
    def test_facet_counts_present(self) -> None:
        from mcp_catalog.server import get_catalog_stats

        result = get_catalog_stats()
        counts = result["facet_value_counts"]
        assert "platform" in counts
        assert "measurement" in counts
        assert counts["platform"] == 2  # BDC, AnVIL
