"""Concept index — loads classification output and catalog metadata, provides search."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from importlib.resources import files as pkg_files
from pathlib import Path

import numpy as np

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
            repo_root / "catalog-build" / "classification" / "output" / "llm-concepts-v4",
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


def _resolve_demographics_path() -> Path:
    """Resolve the path to demographic-profiles.json."""
    explicit = os.environ.get("NCPI_DEMOGRAPHIC_PROFILES_PATH")
    if explicit:
        return Path(explicit)
    repo_root = _resolve_repo_root()
    return (
        repo_root
        / "catalog-build"
        / "classification"
        / "output"
        / "demographic-profiles.json"
    )


def _load_demographic_mappings() -> dict[str, dict[str, str]]:
    """Load canonical label mappings from the bundled JSON file.

    Returns a dict keyed by dimension (``"sex"``, ``"raceEthnicity"``).
    Each value is a reverse-lookup dict mapping lowercase pattern → canonical label.
    """
    resource = pkg_files("concept_search").joinpath("demographic_mappings.json")
    with resource.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    reverse: dict[str, dict[str, str]] = {}
    for dimension, canonical_map in raw.items():
        lookup: dict[str, str] = {}
        for canonical, patterns in canonical_map.items():
            for pattern in patterns:
                lookup[pattern.lower().strip()] = canonical
        reverse[dimension] = lookup
    return reverse


def _normalize_categories(
    categories: list[dict],
    lookup: dict[str, str],
    fallback: str,
) -> list[dict]:
    """Map verbatim categories to canonical labels, summing counts.

    Args:
        categories: Raw ``[{label, count, ...}]`` from the profile.
        lookup: Lowercase pattern → canonical label mapping.
        fallback: Canonical label for unmapped entries.

    Returns:
        Deduplicated ``[{label, count}]`` sorted by count descending.
    """
    merged: dict[str, int] = defaultdict(int)
    for cat in categories:
        verbatim = cat.get("label", "")
        count = cat.get("count", 0)
        canonical = lookup.get(verbatim.lower().strip(), fallback)
        merged[canonical] += count
    return sorted(
        [{"count": c, "label": lbl} for lbl, c in merged.items()],
        key=lambda x: -x["count"],
    )


def _load_demographic_profiles(
    mappings: dict[str, dict[str, str]],
) -> tuple[dict[str, dict], list[tuple[str, str, str, str]]]:
    """Load and normalize demographic-profiles.json.

    Args:
        mappings: Reverse-lookup mappings from ``_load_demographic_mappings``.

    Returns:
        A tuple of:
        - ``demographics_dict``: dbGapId → lean demographics dict for raw_json
        - ``eav_rows``: ``(db_gap_id, facet, value, value_lower)`` tuples
    """
    path = _resolve_demographics_path()
    if not path.exists():
        return {}, []

    with open(path) as f:
        raw = json.load(f)
    studies = raw.get("studies", {})

    demographics_dict: dict[str, dict] = {}
    eav_rows: list[tuple[str, str, str, str]] = []

    sex_lookup = mappings.get("sex", {})
    race_lookup = mappings.get("raceEthnicity", {})

    dimension_config: list[tuple[str, str, dict[str, str], str]] = [
        ("sex", Facet.SEX.value, sex_lookup, "Other/Unknown"),
        ("raceEthnicity", Facet.RACE_ETHNICITY.value, race_lookup, "Other"),
        ("computedAncestry", Facet.COMPUTED_ANCESTRY.value, {}, ""),
    ]

    for study_id, study_data in studies.items():
        demo: dict[str, dict] = {}
        for dim_key, facet_val, lookup, fallback in dimension_config:
            dist = study_data.get(dim_key)
            if not dist:
                continue
            n = dist.get("n", 0)
            raw_cats = dist.get("categories", [])

            # Normalize (sex/race) or pass through (computedAncestry)
            if lookup:
                cats = _normalize_categories(raw_cats, lookup, fallback)
            else:
                cats = sorted(
                    [{"count": c.get("count", 0), "label": c.get("label", "")}
                     for c in raw_cats],
                    key=lambda x: -x["count"],
                )

            # Drop categories with zero or negative counts to avoid
            # false-positive EAV rows (e.g., sex=Female with count=0).
            cats = [c for c in cats if c["count"] > 0 and c["label"]]

            # Pre-compute percent
            for cat in cats:
                cat["percent"] = round(cat["count"] / n * 100, 1) if n > 0 else 0.0

            demo[dim_key] = {"categories": cats, "n": n}

            # EAV rows for each canonical label
            for cat in cats:
                label = cat["label"]
                eav_rows.append((study_id, facet_val, label, label.lower()))

        if demo:
            demographics_dict[study_id] = demo

    return demographics_dict, eav_rows


def _resolve_isa_path() -> Path:
    """Resolve the path to concept-isa.json."""
    explicit = os.environ.get("NCPI_CONCEPT_ISA_PATH")
    if explicit:
        return Path(explicit)
    repo_root = _resolve_repo_root()
    return (
        repo_root
        / "catalog-build"
        / "classification"
        / "output"
        / "concept-isa.json"
    )


def _resolve_focus_isa_path() -> Path:
    """Resolve the path to focus_isa.json (bundled with this package)."""
    return Path(__file__).parent / "focus_isa.json"


def _load_concept_descriptions() -> dict[str, dict]:
    """Load concept names and descriptions from all vocabulary sources.

    Merges TOPMed (concept-vocabulary.json), PhenX (phenx-concept-vocabulary.json),
    and NCPI categories (ncpi-categories.json) into a single lookup keyed by
    namespaced concept_id.

    Returns:
        Dict mapping concept_id → {"name": ..., "description": ...}.
    """
    repo_root = _resolve_repo_root()
    vocab_dir = repo_root / "catalog-build" / "classification" / "output"

    descriptions: dict[str, dict] = {}

    # Build a set of known namespaced IDs from the ISA table so we can
    # resolve bare concept_ids to their correct namespace.
    isa_path = _resolve_isa_path()
    known_ids: set[str] = set()
    if isa_path.exists():
        with open(isa_path) as f:
            for entry in json.load(f):
                known_ids.add(entry["child"])
                known_ids.add(entry["parent"])

    # TOPMed/catalog concepts (bare concept_id → resolve namespace via ISA)
    topmed_path = vocab_dir / "concept-vocabulary.json"
    if topmed_path.exists():
        with open(topmed_path) as f:
            for entry in json.load(f):
                bare = entry.get("concept_id", "")
                # Already namespaced?
                if ":" in bare:
                    cid = bare
                else:
                    # Check ISA for the correct namespace
                    candidates = [k for k in known_ids if k.endswith(f":{bare}")]
                    cid = candidates[0] if len(candidates) == 1 else f"topmed:{bare}"
                desc_entry: dict[str, str] = {
                    "description": entry.get("description", ""),
                    "name": entry.get("name", cid),
                }
                if entry.get("type"):
                    desc_entry["type"] = entry["type"]
                descriptions[cid] = desc_entry

    # PhenX concepts (already namespaced)
    phenx_path = vocab_dir / "phenx-concept-vocabulary.json"
    if phenx_path.exists():
        with open(phenx_path) as f:
            for entry in json.load(f):
                cid = entry.get("concept_id", "")
                descriptions[cid] = {
                    "description": entry.get("description", ""),
                    "name": entry.get("name", cid),
                }

    # NCPI categories (already namespaced)
    ncpi_path = vocab_dir / "ncpi-categories.json"
    if ncpi_path.exists():
        with open(ncpi_path) as f:
            for entry in json.load(f):
                cid = entry.get("concept_id", "")
                descriptions[cid] = {
                    "description": entry.get("description", ""),
                    "name": entry.get("name", cid),
                }

    return descriptions


def _load_isa_table(
    path: Path | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Load ISA (is-a) child→parent relationships.

    Args:
        path: Path to a ``[{child, parent}]`` JSON file.  Falls back
            to the concept-isa.json resolved via ``_resolve_isa_path()``.

    Returns:
        Tuple of:
        - parents: child concept_id → list of parent concept_ids
        - children: parent concept_id → list of child concept_ids
    """
    if path is None:
        path = _resolve_isa_path()
    if not path.exists():
        return {}, {}
    with open(path) as f:
        entries = json.load(f)
    parents: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        child = entry["child"]
        parent = entry["parent"]
        parents[child].append(parent)
        children[parent].append(child)
    return dict(parents), dict(children)


def _compute_closure(
    concept_id: str, isa_parents: dict[str, list[str]]
) -> list[str]:
    """Walk the ISA graph upward from a concept to compute its full closure.

    The closure includes the concept itself plus all transitive ancestors.

    Args:
        concept_id: Starting concept (e.g., "topmed:bp_systolic").
        isa_parents: Child → parent mapping from the ISA table.

    Returns:
        List of all concept_ids in the closure (self + ancestors).
    """
    closure: list[str] = []
    visited: set[str] = set()
    stack = [concept_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        closure.append(current)
        for parent in isa_parents.get(current, []):
            if parent not in visited:
                stack.append(parent)
    return closure


class ConceptIndex:
    """In-memory index of facet values with study counts."""

    def __init__(self, store: StudyStore | None = None) -> None:
        # facet -> {lowercase_value: ConceptMatch}
        self._index: dict[Facet, dict[str, ConceptMatch]] = {f: {} for f in Facet}
        # Swappable study store (DuckDB by default)
        self.store: StudyStore = store or DuckDBStore.create_empty()
        # Lazy-loaded supplementary data (populated by load())
        self._consent_descriptions: dict = {}
        self._concept_descriptions: dict[str, dict] = {}
        self._focus_categories: dict[str, list[dict]] = {}
        self._isa_children: dict[str, list[str]] = {}
        self._focus_isa_children: dict[str, list[str]] = {}
        # Embedding search data (populated during build or cache load)
        self._embedding_nodes: list[dict] = []
        self._embedding_matrix: np.ndarray | None = None

    def load(self) -> None:
        """Load data — from cached DuckDB file if available, else from JSON."""
        cache_path = _resolve_cache_path()
        lock_path = cache_path.with_suffix(".lock")

        # Use a file lock so only one process builds the cache; others wait.
        import filelock

        lock = filelock.FileLock(lock_path, timeout=120)
        with lock:
            if cache_path.exists():
                logger.info("Loading from cached DuckDB: %s", cache_path)
                self.store = DuckDBStore.load_from_file(str(cache_path))
                self._rebuild_index_from_store()
                # Load ISA children for drill-down (not stored in DuckDB)
                _, self._isa_children = _load_isa_table()
                _, self._focus_isa_children = _load_isa_table(
                    _resolve_focus_isa_path()
                )
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
        self.load_consent_code_descriptions()
        # Load concept descriptions before _build_concept_embeddings needs them
        # (on cold build, _load_from_json calls _build_concept_embeddings)
        self._concept_descriptions = _load_concept_descriptions()

    def _ensure_concept_descriptions(self) -> dict[str, dict]:
        """Return concept descriptions, loading them if not yet available."""
        if not self._concept_descriptions:
            self._concept_descriptions = _load_concept_descriptions()
        return self._concept_descriptions

    def _load_from_json(self) -> None:
        """Full build path: parse JSON data files and populate the store."""
        llm_dir, studies_path = _resolve_paths()
        self._load_measurement_concepts(llm_dir)

        # Load and normalize demographic profiles
        mappings = _load_demographic_mappings()
        demographics_dict, demo_eav_rows = _load_demographic_profiles(mappings)

        self._load_study_metadata(studies_path, demographics_dict)

        # Insert demographic EAV rows and build index entries
        if isinstance(self.store, DuckDBStore) and demo_eav_rows:
            self.store.load_facet_values_batch(demo_eav_rows)
        demo_counts: dict[Facet, Counter[str]] = {
            Facet.COMPUTED_ANCESTRY: Counter(),
            Facet.RACE_ETHNICITY: Counter(),
            Facet.SEX: Counter(),
        }
        facet_val_map = {
            Facet.COMPUTED_ANCESTRY.value: Facet.COMPUTED_ANCESTRY,
            Facet.RACE_ETHNICITY.value: Facet.RACE_ETHNICITY,
            Facet.SEX.value: Facet.SEX,
        }
        seen: set[tuple[str, str, str]] = set()
        for db_gap_id, facet_str, value, _ in demo_eav_rows:
            key = (db_gap_id, facet_str, value)
            if key not in seen:
                seen.add(key)
                facet = facet_val_map[facet_str]
                demo_counts[facet][value] += 1
        for facet, counts in demo_counts.items():
            for value, count in counts.items():
                self._index[facet][value.lower()] = ConceptMatch(
                    facet=facet,
                    study_count=count,
                    value=value,
                )

        if isinstance(self.store, DuckDBStore):
            self.store.finalize()

        # Build concept embeddings for semantic search
        self._build_concept_embeddings()

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
        try:
            self._load_embeddings_from_store()
        except Exception as exc:
            logger.warning(
                "Could not load concept embeddings from cache "
                "(may be an older cache file): %s",
                exc,
            )

    def _build_concept_embeddings(self) -> None:
        """Generate embeddings for all concept+archetype nodes and store them.

        Uses the already-loaded ``_concept_descriptions`` dict. Each node is
        embedded as ``"name: description"``.  Results are stored in the DuckDB
        ``concept_embeddings`` table and cached in memory for KNN search.

        Gracefully skips if sentence-transformers is not installed (e.g. in
        test environments).
        """
        from . import embeddings

        descs = self._ensure_concept_descriptions()
        if not descs:
            logger.warning("No concept descriptions found — skipping embeddings")
            return

        nodes: list[dict] = []
        texts: list[str] = []
        for cid, info in sorted(descs.items()):
            name = info.get("name", cid)
            desc = info.get("description", "")
            node_type = info.get("type", "concept")
            nodes.append({
                "concept_id": cid,
                "description": desc,
                "name": name,
                "type": node_type,
            })
            texts.append(f"{name}: {desc}" if desc else name)

        logger.info("Embedding %d concept nodes...", len(texts))
        try:
            matrix = embeddings.embed_texts(texts)
        except ImportError:
            logger.warning("sentence-transformers not available — skipping embeddings")
            return
        except Exception:
            logger.exception("Failed to generate concept embeddings — skipping")
            return
        logger.info("Embedding complete: %s", matrix.shape)

        # Store in DuckDB
        if isinstance(self.store, DuckDBStore):
            rows = [
                (n["concept_id"], n["name"], n["description"], n["type"],
                 matrix[i].tolist())
                for i, n in enumerate(nodes)
            ]
            self.store.load_concept_embeddings_batch(rows)

        self._embedding_nodes = nodes
        self._embedding_matrix = matrix

    def _load_embeddings_from_store(self) -> None:
        """Load concept embeddings from the DuckDB cache into memory."""
        if not isinstance(self.store, DuckDBStore):
            return
        rows = self.store.get_concept_embeddings()
        if not rows:
            logger.info("No concept embeddings in cache")
            return
        nodes: list[dict] = []
        vecs: list[list[float]] = []
        for cid, name, desc, node_type, embedding in rows:
            nodes.append({
                "concept_id": cid,
                "description": desc or "",
                "name": name or cid,
                "type": node_type or "concept",
            })
            vecs.append(embedding)
        self._embedding_nodes = nodes
        self._embedding_matrix = np.array(vecs, dtype=np.float32)
        logger.info(
            "Loaded %d concept embeddings from cache", len(nodes)
        )

    def search_concepts_by_embedding(
        self, query: str, top_k: int = 10
    ) -> list[dict]:
        """KNN search against concept+archetype embeddings.

        Args:
            query: Natural-language query (e.g. "blood sugar", "eGFR").
            top_k: Number of results to return.

        Returns:
            Top-K nodes with concept_id, name, description, type,
            similarity, and study_count.
        """
        if self._embedding_matrix is None or len(self._embedding_nodes) == 0:
            return []

        try:
            from . import embeddings
            query_vec = embeddings.embed_query(query)
            hits = embeddings.search_embeddings(
                query_vec, self._embedding_matrix, top_k=top_k
            )
        except Exception:
            logger.exception("Embedding search failed — returning empty")
            return []

        results: list[dict] = []
        for idx, sim in hits:
            node = self._embedding_nodes[idx]
            cid = node["concept_id"]
            match = self._index[Facet.MEASUREMENT].get(cid.lower())
            results.append({
                "concept_id": cid,
                "description": node["description"],
                "name": node["name"],
                "similarity": round(sim, 4),
                "study_count": match.study_count if match else 0,
                "type": node["type"],
            })
        return results

    def _load_measurement_concepts(self, llm_dir: Path) -> None:
        """Load concept names and variable details from per-study LLM JSON.

        Reads v4 format with namespaced concept_ids (``topmed:``, ``phenx:``).
        Computes ISA closure for each variable so that searching a parent
        concept returns all descendant variables.
        """
        if not llm_dir.exists():
            return
        isa_parents, self._isa_children = _load_isa_table()
        concept_studies: dict[str, set[str]] = defaultdict(set)
        study_concepts: dict[str, set[str]] = defaultdict(set)
        variable_rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        for path in sorted(llm_dir.glob("phs*.json")):
            with open(path) as f:
                data = json.load(f)
            study_id = data.get("studyId", path.stem)
            for table in data.get("tables", []):
                dataset_id = table.get("datasetId", "")
                table_name = table.get("tableName", "")
                for var in table.get("variables", []):
                    concept = var.get("concept_id")
                    if concept:
                        # Compute ISA closure (self + all ancestors)
                        closure = _compute_closure(concept, isa_parents)
                        closure_json = json.dumps(
                            [c.lower() for c in closure]
                        )
                        # Track studies for ALL concepts in closure
                        for ancestor in closure:
                            concept_studies[ancestor].add(study_id)
                        study_concepts[study_id].add(concept)
                        variable_rows.append((
                            concept,
                            concept.lower(),
                            var.get("cui", "") or "",
                            closure_json,
                            dataset_id,
                            var.get("description", ""),
                            var.get("id", ""),
                            study_id,
                            table_name,
                            var.get("name", ""),
                        ))
        for concept, studies in concept_studies.items():
            key = concept.lower()
            self._index[Facet.MEASUREMENT][key] = ConceptMatch(
                facet=Facet.MEASUREMENT,
                study_count=len(studies),
                value=concept,
            )
        # Batch-insert measurement facet values and variable rows into the store
        if isinstance(self.store, DuckDBStore):
            facet_val = Facet.MEASUREMENT.value
            # Use concept_studies (already closure-expanded) to build facet
            # rows — avoids recomputing closures.
            rows = [
                (sid, facet_val, concept, concept.lower())
                for concept, sids in concept_studies.items()
                for sid in sids
            ]
            self.store.load_facet_values_batch(rows)
            self.store.load_variables_batch(variable_rows)
            logger.info("Loaded %d variable rows", len(variable_rows))

    def _load_study_metadata(
        self,
        studies_path: Path,
        demographics: dict[str, dict] | None = None,
    ) -> None:
        """Load study metadata and extract facet values.

        Expands focus terms using MeSH ISA hierarchy so that searching
        a parent term also returns studies tagged with descendant terms.

        Args:
            studies_path: Path to ``ncpi-platform-studies.json``.
            demographics: Optional dbGapId → lean demographics dict to merge
                into each study's raw_json before storage.
        """
        if not studies_path.exists():
            return
        with open(studies_path) as f:
            studies_raw = json.load(f)

        demographics = demographics or {}

        # Load focus ISA hierarchy for ancestor expansion
        focus_isa_path = _resolve_focus_isa_path()
        focus_isa_parents, self._focus_isa_children = _load_isa_table(
            focus_isa_path
        )

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
            # Merge demographics into study dict before storage
            demo = demographics.get(dbgap_id)
            if demo is not None:
                study["demographics"] = demo
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
                        # Expand focus terms with ISA ancestors
                        if facet == Facet.FOCUS and focus_isa_parents:
                            ancestors = _compute_closure(v, focus_isa_parents)
                            for anc in ancestors:
                                if anc != v:
                                    facet_counts[facet][anc] += 1
                                    if is_duckdb:
                                        facet_rows.append(
                                            (dbgap_id, facet.value, anc, anc.lower())
                                        )
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
        include: list[tuple[Facet, list[str]]],
        exclude: list[tuple[Facet, list[str]]] | None = None,
    ) -> list[dict]:
        """Find studies matching include constraints minus exclude.

        Delegates to the swappable ``StudyStore`` backend.

        Args:
            include: Constraints to include. Each tuple is one AND
                constraint; values within are OR-ed.
            exclude: Constraints to subtract from results.

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

    def get_measurement_category_concepts(
        self, keyword: str
    ) -> list[ConceptMatch]:
        """Return measurement concepts matching a keyword, sorted by study count.

        Searches the live measurement index keys for substring matches
        against the keyword (converted to underscore slug form).

        Args:
            keyword: Search term (e.g. "blood_pressure", "media",
                     "biomarkers"). Spaces and hyphens are converted to
                     underscores for matching against namespaced concept IDs.

        Returns:
            Measurement concepts as ConceptMatch objects.
        """
        slug = keyword.lower().replace(" ", "_").replace("-", "_")
        results: list[ConceptMatch] = []
        for key, match in self._index[Facet.MEASUREMENT].items():
            if slug in key:
                results.append(match)
        results.sort(key=lambda m: m.study_count, reverse=True)
        return results

    def get_concept_children(self, concept_id: str) -> list[dict]:
        """Return direct child concepts with names, descriptions, and study counts.

        Args:
            concept_id: Parent concept to look up children for.

        Returns:
            Child concepts sorted by study count descending. Each dict has
            concept_id, name, description, and study_count.
        """
        children = self._isa_children.get(concept_id, [])
        results = []
        for child_id in children:
            desc = self._concept_descriptions.get(child_id, {})
            match = self._index[Facet.MEASUREMENT].get(child_id.lower())
            entry: dict = {
                "concept_id": child_id,
                "description": desc.get("description", ""),
                "name": desc.get("name", child_id),
                "study_count": match.study_count if match else 0,
            }
            if desc.get("type"):
                entry["type"] = desc["type"]
            results.append(entry)
        return sorted(results, key=lambda x: -x["study_count"])

    def list_variables_for_concept(
        self, concept_id: str, limit: int = 200
    ) -> list[dict]:
        """Return distinct variables under a concept with descriptions.

        Delegates to the store's ``list_variables_for_concept`` method.

        Args:
            concept_id: Concept to list variables for.
            limit: Maximum number of variables to return.

        Returns:
            Distinct (variable_name, description) dicts.
        """
        if isinstance(self.store, DuckDBStore):
            return self.store.list_variables_for_concept(concept_id, limit=limit)
        return []

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
