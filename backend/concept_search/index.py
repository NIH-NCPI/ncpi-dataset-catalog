"""Concept index — loads classification output and catalog metadata, provides search."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from .models import ConceptMatch, Facet


def _resolve_paths() -> tuple[Path, Path]:
    """Resolve data paths at call time (after dotenv is loaded).

    Reads NCPI_REPO_ROOT, NCPI_LLM_CONCEPTS_DIR, NCPI_PLATFORM_STUDIES_PATH
    from environment, falling back to paths relative to this package.
    """
    repo_root = Path(
        os.environ.get(
            "NCPI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent
        )
    )
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


class ConceptIndex:
    """In-memory index of facet values with study counts."""

    def __init__(self) -> None:
        # facet -> {lowercase_value: ConceptMatch}
        self._index: dict[Facet, dict[str, ConceptMatch]] = {f: {} for f in Facet}
        # study_id -> set of concept names (for measurement lookup)
        self._study_concepts: dict[str, set[str]] = defaultdict(set)
        # study_id -> study metadata dict
        self._studies: dict[str, dict] = {}

    def load(self) -> None:
        """Load all data sources and build the index."""
        llm_dir, studies_path = _resolve_paths()
        self._load_measurement_concepts(llm_dir)
        self._load_study_metadata(studies_path)
        self.load_focus_categories()

    def _load_measurement_concepts(self, llm_dir: Path) -> None:
        """Load concept names from per-study LLM classification JSON files."""
        if not llm_dir.exists():
            return
        concept_studies: dict[str, set[str]] = defaultdict(set)
        for path in sorted(llm_dir.glob("phs*.json")):
            with open(path) as f:
                data = json.load(f)
            study_id = data.get("studyId", path.stem)
            for table in data.get("tables", []):
                for var in table.get("variables", []):
                    concept = var.get("concept")
                    if concept:
                        concept_studies[concept].add(study_id)
                        self._study_concepts[study_id].add(concept)
        for concept, studies in concept_studies.items():
            key = concept.lower()
            self._index[Facet.MEASUREMENT][key] = ConceptMatch(
                facet=Facet.MEASUREMENT,
                study_count=len(studies),
                value=concept,
            )

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
        for study in studies_raw.values():
            dbgap_id = study.get("dbGapId", "")
            self._studies[dbgap_id] = study
            for facet, field in facet_field_map.items():
                raw = study.get(field)
                if raw is None:
                    continue
                values = raw if isinstance(raw, list) else [raw]
                for v in values:
                    if v:
                        facet_counts[facet][v] += 1

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

    def get_studies_for_mentions(
        self, facet_values: dict[Facet, list[str]]
    ) -> list[dict]:
        """Find studies matching all facet constraints (AND across facets).

        Args:
            facet_values: Mapping of facet to list of required values.

        Returns:
            Studies matching all constraints.
        """
        matching_ids: set[str] | None = None
        facet_field_map: dict[Facet, str] = {
            Facet.CONSENT_CODE: "consentCodes",
            Facet.DATA_TYPE: "dataTypes",
            Facet.FOCUS: "focus",
            Facet.PLATFORM: "platforms",
            Facet.STUDY_DESIGN: "studyDesigns",
        }
        for facet, values in facet_values.items():
            if not values:
                continue
            values_lower = {v.lower() for v in values}
            ids_for_facet: set[str] = set()
            if facet == Facet.MEASUREMENT:
                # Match studies that have any of the requested concepts
                for sid, concepts in self._study_concepts.items():
                    concepts_lower = {c.lower() for c in concepts}
                    if values_lower & concepts_lower:
                        ids_for_facet.add(sid)
            else:
                field = facet_field_map.get(facet)
                if not field:
                    continue
                for sid, study in self._studies.items():
                    raw = study.get(field)
                    if raw is None:
                        continue
                    study_vals = raw if isinstance(raw, list) else [raw]
                    study_vals_lower = {v.lower() for v in study_vals if v}
                    if values_lower & study_vals_lower:
                        ids_for_facet.add(sid)
            if matching_ids is None:
                matching_ids = ids_for_facet
            else:
                matching_ids &= ids_for_facet

        if not matching_ids:
            return []
        return [
            self._studies[sid]
            for sid in sorted(matching_ids)
            if sid in self._studies
        ]

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
