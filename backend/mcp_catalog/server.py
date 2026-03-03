"""FastMCP server with NCPI catalog discovery tools.

Imports ``ConceptIndex``, ``DuckDBStore``, and ``consent_logic`` directly —
no HTTP server or API keys needed. The AI assistant calling the tools
provides the natural language layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from concept_search import consent_logic
from concept_search.index import ConceptIndex, get_index
from concept_search.models import Facet
from concept_search.store import DuckDBStore

mcp = FastMCP("ncpi-catalog")

# ---------------------------------------------------------------------------
# Lazy singleton — ~2 s load from cached DuckDB, only on first tool call
# ---------------------------------------------------------------------------

_index: ConceptIndex | None = None


def _get_index() -> ConceptIndex:
    global _index  # noqa: PLW0603
    if _index is None:
        _index = get_index()
    return _index


# ---------------------------------------------------------------------------
# Tool 1: browse_concepts
# ---------------------------------------------------------------------------

_CATEGORIES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "catalog-build"
    / "classification"
    / "output"
    / "ncpi-categories.json"
)

_categories_cache: list[dict] | None = None


def _get_categories() -> list[dict]:
    global _categories_cache  # noqa: PLW0603
    if _categories_cache is None:
        with open(_CATEGORIES_PATH) as f:
            _categories_cache = json.load(f)
    return _categories_cache


@mcp.tool()
def browse_concepts() -> list[dict]:
    """List the top-level NCPI measurement categories.

    Returns the ~20 broad categories (e.g. Biomarkers, Imaging, Sleep)
    with study counts — a good starting point for exploring what the
    catalog measures.
    """
    index = _get_index()
    categories = _get_categories()

    measurement_idx = index._index[Facet.MEASUREMENT]
    results = []
    for cat in categories:
        cid = cat["concept_id"]
        match = measurement_idx.get(cid.lower())
        results.append({
            "concept_id": cid,
            "description": cat.get("description", ""),
            "name": cat.get("name", cid),
            "study_count": match.study_count if match else 0,
        })
    results.sort(key=lambda x: -x["study_count"])
    return results


# ---------------------------------------------------------------------------
# Tool 2: get_concept_children
# ---------------------------------------------------------------------------


@mcp.tool()
def get_concept_children(concept_id: str) -> list[dict]:
    """Get child concepts under a parent concept.

    Use after browse_concepts() to drill into a category, e.g.
    get_concept_children("ncpi:biomarkers") returns sub-categories
    like blood_pressure, lipids, glucose, etc.

    Args:
        concept_id: Parent concept ID (e.g. "ncpi:biomarkers").
    """
    index = _get_index()
    return index.get_concept_children(concept_id)


# ---------------------------------------------------------------------------
# Tool 3: search_concepts
# ---------------------------------------------------------------------------


@mcp.tool()
def search_concepts(
    query: str,
    facet: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search for concepts/values across the catalog by keyword.

    Searches across all facets (measurement, platform, focus, dataType,
    studyDesign, consentCode, sex, raceEthnicity, computedAncestry)
    or a single facet.

    Args:
        query: Search string (e.g. "diabetes", "blood pressure", "WGS").
        facet: Optional facet to restrict search to (e.g. "measurement",
               "focus", "platform"). Omit to search all facets.
        limit: Maximum results to return (default 20).
    """
    index = _get_index()
    matches = index.search_concepts(query, facet=facet, limit=limit)
    return [
        {"facet": m.facet.value, "study_count": m.study_count, "value": m.value}
        for m in matches
    ]


# ---------------------------------------------------------------------------
# Tool 4: search_studies
# ---------------------------------------------------------------------------

# Map param names to Facet enum values.
_STUDY_FACET_MAP = {
    "consent_code": Facet.CONSENT_CODE,
    "data_type": Facet.DATA_TYPE,
    "focus": Facet.FOCUS,
    "measurement": Facet.MEASUREMENT,
    "platform": Facet.PLATFORM,
    "study_design": Facet.STUDY_DESIGN,
}


@mcp.tool()
def search_studies(
    platform: list[str] | None = None,
    data_type: list[str] | None = None,
    focus: list[str] | None = None,
    measurement: list[str] | None = None,
    study_design: list[str] | None = None,
    consent_code: list[str] | None = None,
) -> dict:
    """Search for studies by faceted criteria. All provided facets are AND-ed;
    values within a facet are OR-ed.

    Use search_concepts() first to discover valid values for each facet.

    Args:
        platform: Filter by platform (e.g. ["BDC", "AnVIL"]).
        data_type: Filter by data type (e.g. ["WGS", "WES", "RNA-Seq"]).
        focus: Filter by disease focus (e.g. ["Asthma"]).
        measurement: Filter by measurement concept (e.g. ["ncpi:biomarkers"]).
        study_design: Filter by study design (e.g. ["Longitudinal Cohort"]).
        consent_code: Filter by consent code (e.g. ["GRU", "HMB"]).
    """
    params = {
        "consent_code": consent_code,
        "data_type": data_type,
        "focus": focus,
        "measurement": measurement,
        "platform": platform,
        "study_design": study_design,
    }
    include: list[tuple[Facet, list[str]]] = []
    for key, values in params.items():
        if values:
            include.append((_STUDY_FACET_MAP[key], values))

    if not include:
        return {"error": "At least one filter is required.", "studies": [], "total": 0}

    index = _get_index()
    raw_studies = index.query_studies(include)

    # Return lean summaries (no full raw_json).
    studies = []
    for s in raw_studies:
        studies.append({
            "consentCodes": s.get("consentCodes", []),
            "dataTypes": s.get("dataTypes", []),
            "dbGapId": s.get("dbGapId", ""),
            "focus": s.get("focus", []),
            "participantCount": s.get("participantCount", 0),
            "platforms": s.get("platforms", []),
            "studyDesigns": s.get("studyDesigns", []),
            "title": s.get("title", ""),
        })

    return {"studies": studies, "total": len(studies)}


# ---------------------------------------------------------------------------
# Tool 5: search_variables
# ---------------------------------------------------------------------------


@mcp.tool()
def search_variables(
    concepts: list[str],
    study_ids: list[str] | None = None,
    limit: int = 100,
) -> dict:
    """Search for measured variables by concept and optionally by study.

    Returns individual dbGaP variables (phv IDs) with descriptions,
    grouped by study. Use get_concept_children() to find specific
    concept IDs to search.

    Args:
        concepts: Concept IDs to search for (e.g. ["ncpi:biomarkers",
                  "topmed:bp_systolic"]). Uses ISA closure so a parent
                  concept returns all descendant variables.
        study_ids: Optional list of dbGaP IDs to restrict results to.
        limit: Maximum variables to return (default 100).
    """
    index = _get_index()
    store = index.store
    if not isinstance(store, DuckDBStore):
        return {"error": "Variable search requires DuckDB store.", "total": 0, "variables": []}

    study_set = set(study_ids) if study_ids else None
    rows, total = store.query_variables(
        concepts=concepts,
        limit=limit,
        study_ids=study_set,
    )

    return {"total": total, "variables": rows}


# ---------------------------------------------------------------------------
# Tool 6: get_study
# ---------------------------------------------------------------------------


@mcp.tool()
def get_study(dbgap_id: str) -> dict | None:
    """Get full details for a single study by its dbGaP accession ID.

    Returns the complete study record including title, platforms,
    focus areas, data types, consent codes, participant count,
    and demographics (if available).

    Args:
        dbgap_id: The dbGaP study accession (e.g. "phs000007").
    """
    index = _get_index()
    store = index.store
    if not isinstance(store, DuckDBStore):
        return None
    return store.get_study(dbgap_id)


# ---------------------------------------------------------------------------
# Tool 7: list_facet_values
# ---------------------------------------------------------------------------


@mcp.tool()
def list_facet_values(facet: str) -> list[dict]:
    """List all values for a given facet, sorted by study count.

    Valid facets: measurement, platform, focus, dataType, studyDesign,
    consentCode, sex, raceEthnicity, computedAncestry.

    Args:
        facet: Facet name (e.g. "platform", "dataType").
    """
    index = _get_index()
    matches = index.list_facet_values(facet)
    return [
        {"study_count": m.study_count, "value": m.value}
        for m in matches
    ]


# ---------------------------------------------------------------------------
# Tool 8: compute_consent_eligibility
# ---------------------------------------------------------------------------


@mcp.tool()
def compute_consent_eligibility(
    purpose: str = "general",
    disease: str | None = None,
    is_nonprofit: bool | None = None,
    explicit_code: str | None = None,
) -> dict:
    """Compute which consent codes allow a given research use case.

    Determines which GA4GH consent codes are eligible based on research
    purpose and constraints. Useful for answering "what data can I use
    for diabetes research?" or "which studies allow commercial use?".

    Args:
        purpose: Research purpose — "general", "health", or "disease".
        disease: Disease name or abbreviation when purpose is "disease"
                 (e.g. "diabetes", "CVD", "breast cancer").
        is_nonprofit: True to include all codes; False to exclude codes
                      with NPU (non-profit use only) modifier; None to
                      include all.
        explicit_code: When set, uses prefix matching instead of purpose
                       logic (e.g. "GRU" matches "GRU", "GRU-IRB").
    """
    index = _get_index()

    # Resolve disease name to abbreviation if provided.
    resolved_disease = None
    disease_info = {}
    if disease:
        resolved_disease = consent_logic.resolve_disease_name(disease)
        disease_info = {
            "input": disease,
            "resolved_abbreviation": resolved_disease,
        }

    # Get all consent code values from the index.
    all_codes = [
        m.value
        for m in index.list_facet_values(Facet.CONSENT_CODE.value)
    ]

    eligible = consent_logic.compute_eligible_codes(
        all_codes,
        purpose=purpose,
        disease=resolved_disease,
        is_nonprofit=is_nonprofit,
        explicit_code=explicit_code,
    )

    return {
        "disease": disease_info if disease_info else None,
        "eligible_codes": eligible,
        "is_nonprofit": is_nonprofit,
        "purpose": purpose,
        "total_eligible": len(eligible),
    }


# ---------------------------------------------------------------------------
# Tool 9: get_catalog_stats
# ---------------------------------------------------------------------------


@mcp.tool()
def get_catalog_stats() -> dict:
    """Get summary statistics about the NCPI catalog.

    Returns the number of distinct values per facet (e.g. how many
    platforms, data types, measurement concepts, etc.) and the
    total study count.
    """
    index = _get_index()
    store = index.store
    study_count = store.study_count if isinstance(store, DuckDBStore) else 0
    return {
        "facet_value_counts": index.stats,
        "study_count": study_count,
    }
