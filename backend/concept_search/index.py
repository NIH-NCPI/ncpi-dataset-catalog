"""Concept index — loads classification output and catalog metadata, provides search."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

from .models import ConceptMatch, Facet
from .store import DuckDBStore, StudyStore

logger = logging.getLogger(__name__)


def _resolve_repo_root() -> Path:
    """Resolve the repo root from NCPI_REPO_ROOT env var or relative to this file."""
    return Path(
        os.environ.get(
            "NCPI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent
        )
    )


def _resolve_paths() -> tuple[Path, Path]:
    """Resolve data paths at call time (after dotenv is loaded).

    Reads NCPI_REPO_ROOT, NCPI_LLM_CONCEPTS_DIR, NCPI_PLATFORM_STUDIES_PATH
    from environment, falling back to paths relative to this package.
    """
    repo_root = _resolve_repo_root()
    llm_dir = Path(
        os.environ.get(
            "NCPI_LLM_CONCEPTS_DIR",
            repo_root / "catalog-build" / "classification" / "output" / "llm-concepts",
        )
    )
    studies_path = Path(
        os.environ.get(
            "NCPI_PLATFORM_STUDIES_PATH",
            repo_root / "catalog" / "ncpi-platform-studies.json",
        )
    )
    return llm_dir, studies_path


def _resolve_cache_path() -> Path:
    """Resolve the DuckDB cache file path."""
    explicit = os.environ.get("NCPI_DUCKDB_CACHE_PATH")
    if explicit:
        return Path(explicit)
    repo_root = _resolve_repo_root()
    return repo_root / "catalog" / "concept-search.duckdb"


class ConceptIndex:
    """In-memory index of facet values with study counts."""

    def __init__(self, store: StudyStore | None = None) -> None:
        # facet -> {lowercase_value: ConceptMatch}
        self._index: dict[Facet, dict[str, ConceptMatch]] = {f: {} for f in Facet}
        # Swappable study store (DuckDB by default)
        self.store: StudyStore = store or DuckDBStore.create_empty()
        # Lazy-loaded supplementary data (populated by load())
        self._consent_descriptions: dict = {}
        self._focus_categories: dict[str, list[dict]] = {}
        self._measurement_hierarchy: dict[str, dict[str, list[dict]]] = {}

    def load(self) -> None:
        """Load data — from cached DuckDB file if available, else from JSON."""
        cache_path = _resolve_cache_path()
        if cache_path.exists():
            logger.info("Loading from cached DuckDB: %s", cache_path)
            self.store = DuckDBStore.load_from_file(str(cache_path))
            self._rebuild_index_from_store()
        else:
            self._load_from_json()
            # Save cache for next startup
            if isinstance(self.store, DuckDBStore):
                try:
                    self.store.save_to_file(cache_path)
                    logger.info("Saved DuckDB cache: %s", cache_path)
                except OSError:
                    logger.warning(
                        "Could not save DuckDB cache to %s", cache_path
                    )
        # These are small JSON files bundled with the package — always load
        self.load_focus_categories()
        self.load_measurement_hierarchy()
        self.load_consent_code_descriptions()

    def _load_from_json(self) -> None:
        """Full build path: parse JSON data files and populate the store."""
        llm_dir, studies_path = _resolve_paths()
        self._load_measurement_concepts(llm_dir)
        self._load_study_metadata(studies_path)
        if isinstance(self.store, DuckDBStore):
            self.store.finalize()

    def _rebuild_index_from_store(self) -> None:
        """Rebuild the in-memory _index from a loaded DuckDB store."""
        if not isinstance(self.store, DuckDBStore):
            return
        for facet_str, value, count in self.store.get_facet_value_counts():
            try:
                facet = Facet(facet_str)
            except ValueError:
                continue
            self._index[facet][value.lower()] = ConceptMatch(
                facet=facet,
                study_count=count,
                value=value,
            )

    def _load_measurement_concepts(self, llm_dir: Path) -> None:
        """Load concept names from per-study LLM classification JSON files."""
        if not llm_dir.exists():
            return
        concept_studies: dict[str, set[str]] = defaultdict(set)
        study_concepts: dict[str, set[str]] = defaultdict(set)
        for path in sorted(llm_dir.glob("phs*.json")):
            with open(path) as f:
                data = json.load(f)
            study_id = data.get("studyId", path.stem)
            for table in data.get("tables", []):
                for var in table.get("variables", []):
                    concept = var.get("concept")
                    if concept:
                        concept_studies[concept].add(study_id)
                        study_concepts[study_id].add(concept)
        for concept, studies in concept_studies.items():
            key = concept.lower()
            self._index[Facet.MEASUREMENT][key] = ConceptMatch(
                facet=Facet.MEASUREMENT,
                study_count=len(studies),
                value=concept,
            )
        # Batch-insert measurement facet values into the store
        if isinstance(self.store, DuckDBStore):
            facet_val = Facet.MEASUREMENT.value
            rows = [
                (sid, facet_val, concept, concept.lower())
                for sid, concepts in study_concepts.items()
                for concept in concepts
            ]
            self.store.load_facet_values_batch(rows)

    def _load_study_metadata(self, studies_path: Path) -> None:
        """Load study metadata and extract facet values."""
        if not studies_path.exists():
            return
        with open(studies_path) as f:
            studies_raw = json.load(f)

        # Count occurrences per facet value
        facet_counts: dict[Facet, Counter[str]] = {f: Counter() for f in Facet}
        facet_field_map: dict[Facet, str] = {
            Facet.CONSENT_CODE: "consentCodes",
            Facet.DATA_TYPE: "dataTypes",
            Facet.FOCUS: "focus",
            Facet.PLATFORM: "platforms",
            Facet.STUDY_DESIGN: "studyDesigns",
        }
        is_duckdb = isinstance(self.store, DuckDBStore)
        study_rows: list[tuple[str, dict]] = []
        facet_rows: list[tuple[str, str, str, str]] = []
        for study in studies_raw.values():
            dbgap_id = study.get("dbGapId", "")
            if is_duckdb:
                study_rows.append((dbgap_id, study))
            for facet, field in facet_field_map.items():
                raw = study.get(field)
                if raw is None:
                    continue
                values = raw if isinstance(raw, list) else [raw]
                for v in values:
                    if v:
                        facet_counts[facet][v] += 1
                        if is_duckdb:
                            facet_rows.append((dbgap_id, facet.value, v, v.lower()))
        if is_duckdb:
            self.store.load_studies_batch(study_rows)
            self.store.load_facet_values_batch(facet_rows)

        # Build index entries for non-measurement facets
        for facet, counts in facet_counts.items():
            if facet == Facet.MEASUREMENT:
                continue
            for value, count in counts.items():
                key = value.lower()
                self._index[facet][key] = ConceptMatch(
                    facet=facet,
                    study_count=count,
                    value=value,
                )

    def search_concepts(
        self, query: str, facet: str | None = None, limit: int = 20
    ) -> list[ConceptMatch]:
        """Case-insensitive substring search across facet values.

        Args:
            query: Search string.
            facet: If provided, search only this facet. Use Facet enum value
                   (e.g. "measurement", "focus").
            limit: Max results to return.

        Returns:
            Matching concepts sorted by study count descending.
        """
        query_lower = query.lower()
        results: list[ConceptMatch] = []
        facets_to_search: list[Facet]
        if facet:
            try:
                facets_to_search = [Facet(facet)]
            except ValueError:
                return []
        else:
            facets_to_search = list(Facet)

        for f in facets_to_search:
            for key, match in self._index[f].items():
                if query_lower in key:
                    results.append(match)

        results.sort(key=lambda m: m.study_count, reverse=True)
        return results[:limit]

    def list_facet_values(self, facet: str) -> list[ConceptMatch]:
        """List all values for a facet, sorted by study count descending."""
        try:
            f = Facet(facet)
        except ValueError:
            return []
        values = list(self._index[f].values())
        values.sort(key=lambda m: m.study_count, reverse=True)
        return values

    def query_studies(
        self,
        include: dict[Facet, list[str]],
        exclude: dict[Facet, list[str]] | None = None,
    ) -> list[dict]:
        """Find studies matching include constraints minus exclude.

        Delegates to the swappable ``StudyStore`` backend.

        Args:
            include: Facet constraints to include (AND between, OR within).
            exclude: Facet constraints to subtract from results.

        Returns:
            Studies matching all constraints.
        """
        return self.store.query_studies(include, exclude)

    def load_focus_categories(self) -> None:
        """Load the MeSH-based focus category mapping."""
        cat_path = Path(__file__).parent / "focus_categories.json"
        if not cat_path.exists():
            self._focus_categories: dict[str, list[dict]] = {}
            return
        with open(cat_path) as f:
            data = json.load(f)
        self._focus_categories = data.get("categories", {})

    def list_focus_categories(self) -> list[str]:
        """Return sorted list of focus category names."""
        return sorted(self._focus_categories.keys())

    def get_focus_category_terms(self, category: str) -> list[ConceptMatch]:
        """Return all focus terms in a category, sorted by study count.

        Args:
            category: Category name (e.g. "Cardiovascular Diseases").

        Returns:
            Focus terms in this category as ConceptMatch objects.
        """
        terms = self._focus_categories.get(category, [])
        return [
            ConceptMatch(facet=Facet.FOCUS, study_count=t["study_count"], value=t["term"])
            for t in terms
        ]

    def load_consent_code_descriptions(self) -> None:
        """Load consent code description data for drill-down."""
        desc_path = Path(__file__).parent / "consent_codes.json"
        if not desc_path.exists():
            self._consent_descriptions: dict = {}
            return
        with open(desc_path) as f:
            self._consent_descriptions = json.load(f)

    def get_consent_code_categories(self) -> dict:
        """Return top-level consent code categories with descriptions and study counts.

        Returns the base codes (GRU, HMB, DS, etc.) with their descriptions
        and total study counts, plus the modifier definitions.
        """
        base_codes = self._consent_descriptions.get("base_codes", {})
        modifiers = self._consent_descriptions.get("modifiers", {})

        # Aggregate study counts by base code
        base_counts: dict[str, int] = defaultdict(int)
        for match in self._index[Facet.CONSENT_CODE].values():
            base = match.value.split("-")[0]
            base_counts[base] += match.study_count

        categories = []
        for code, description in base_codes.items():
            categories.append({
                "code": code,
                "description": description,
                "total_studies": base_counts.get(code, 0),
            })
        # Sort by study count
        categories.sort(key=lambda x: -x["total_studies"])

        return {
            "base_codes": categories,
            "modifiers": [
                {"code": k, "description": v} for k, v in modifiers.items()
            ],
        }

    def get_consent_codes_for_base(
        self, base_code: str, limit: int = 20
    ) -> list[dict]:
        """Return all consent code variants for a base code.

        Args:
            base_code: The base code prefix (e.g. "GRU", "HMB", "DS-CVD").

        Returns:
            Matching codes with study counts, sorted by count.
        """
        prefix = base_code.lower()
        results = []
        for key, match in self._index[Facet.CONSENT_CODE].items():
            # Match exact base or base- prefix
            if key == prefix or key.startswith(prefix + "-"):
                results.append({
                    "code": match.value,
                    "study_count": match.study_count,
                })
        results.sort(key=lambda x: -x["study_count"])
        return results[:limit]

    def get_disease_specific_codes(self) -> list[dict]:
        """Return all DS-* disease abbreviations with descriptions and study counts.

        Returns:
            Disease codes with their full names and total study counts.
        """
        disease_abbrevs = self._consent_descriptions.get(
            "disease_abbreviations", {}
        )
        # Aggregate counts per disease abbreviation
        disease_counts: dict[str, int] = defaultdict(int)
        for match in self._index[Facet.CONSENT_CODE].values():
            code = match.value
            if not code.startswith("DS-"):
                continue
            # Extract disease part (everything between DS- and first modifier)
            modifiers = self._consent_descriptions.get("modifiers", {})
            parts = code.split("-")[1:]  # drop "DS"
            disease_parts = []
            for part in parts:
                if part in modifiers:
                    break
                disease_parts.append(part)
            disease_key = "-".join(disease_parts)
            if disease_key:
                disease_counts[disease_key] += match.study_count

        results = []
        for abbrev, count in disease_counts.items():
            results.append({
                "abbreviation": abbrev,
                "disease": disease_abbrevs.get(abbrev, abbrev),
                "code_prefix": f"DS-{abbrev}",
                "total_studies": count,
            })
        results.sort(key=lambda x: -x["total_studies"])
        return results

    def load_measurement_hierarchy(self) -> None:
        """Load the LLM-built measurement concept hierarchy."""
        hierarchy_path = self._resolve_hierarchy_path()
        if not hierarchy_path.exists():
            self._measurement_hierarchy: dict[str, dict[str, list[dict]]] = {}
            return
        with open(hierarchy_path) as f:
            data = json.load(f)
        self._measurement_hierarchy = data.get("hierarchy", {})

    @staticmethod
    def _resolve_hierarchy_path() -> Path:
        """Resolve the path to concept-hierarchy.json."""
        repo_root = Path(
            os.environ.get(
                "NCPI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent
            )
        )
        return Path(
            os.environ.get(
                "NCPI_CONCEPT_HIERARCHY_PATH",
                repo_root
                / "catalog-build"
                / "classification"
                / "output"
                / "concept-hierarchy.json",
            )
        )

    def list_measurement_categories(self) -> dict[str, list[str]]:
        """Return top-level categories with their mid-level subcategories.

        Returns:
            Dict of top_level -> sorted list of mid_level names.
        """
        return {
            tl: sorted(mids.keys())
            for tl, mids in sorted(self._measurement_hierarchy.items())
        }

    def get_measurement_category_concepts(
        self, top_level: str, mid_level: str | None = None
    ) -> list[ConceptMatch]:
        """Return measurement concepts in a category, sorted by study count.

        Args:
            top_level: Top-level category (e.g. "Cardiovascular").
            mid_level: Optional mid-level subcategory (e.g. "Blood Pressure").
                       If omitted, returns all concepts in the top-level.

        Returns:
            Measurement concepts as ConceptMatch objects.
        """
        tl_data = self._measurement_hierarchy.get(top_level, {})
        if mid_level:
            concepts = tl_data.get(mid_level, [])
        else:
            concepts = [c for mids in tl_data.values() for c in mids]
        return [
            ConceptMatch(
                facet=Facet.MEASUREMENT,
                study_count=c["study_count"],
                value=c["concept"],
            )
            for c in concepts
        ]

    @property
    def stats(self) -> dict[str, int]:
        """Return count of values per facet."""
        return {f.value: len(entries) for f, entries in self._index.items()}


# Module-level singleton
_index: ConceptIndex | None = None


def get_index() -> ConceptIndex:
    """Get or create the shared ConceptIndex singleton."""
    global _index  # noqa: PLW0603
    if _index is None:
        _index = ConceptIndex()
        _index.load()
    return _index
