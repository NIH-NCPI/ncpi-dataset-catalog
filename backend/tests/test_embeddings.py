"""Unit tests for embedding utilities and DuckDB embedding persistence.

Covers search_embeddings edge cases and concept_embeddings table round-trip.
No real model loading — uses synthetic vectors.
"""

from __future__ import annotations

import numpy as np
import pytest

from concept_search.embeddings import search_embeddings
from concept_search.store import DuckDBStore


# ---------------------------------------------------------------------------
# search_embeddings: edge cases
# ---------------------------------------------------------------------------


class TestSearchEmbeddings:
    """Edge-case tests for cosine KNN search."""

    @pytest.fixture
    def matrix(self) -> np.ndarray:
        """3 unit vectors in 4-D for easy manual verification."""
        vecs = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ], dtype=np.float32)
        return vecs

    def test_basic_topk(self, matrix: np.ndarray) -> None:
        """Top-1 returns the most similar vector."""
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        results = search_embeddings(query, matrix, top_k=1)
        assert len(results) == 1
        assert results[0][0] == 0  # index of the matching vector
        assert results[0][1] == pytest.approx(1.0)

    def test_top_k_zero_returns_empty(self, matrix: np.ndarray) -> None:
        """top_k=0 returns an empty list."""
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert search_embeddings(query, matrix, top_k=0) == []

    def test_top_k_negative_returns_empty(self, matrix: np.ndarray) -> None:
        """top_k=-1 returns an empty list."""
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert search_embeddings(query, matrix, top_k=-1) == []

    def test_empty_matrix_returns_empty(self) -> None:
        """Empty node matrix returns an empty list."""
        empty = np.zeros((0, 4), dtype=np.float32)
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert search_embeddings(query, empty, top_k=5) == []

    def test_top_k_larger_than_matrix(self, matrix: np.ndarray) -> None:
        """top_k > num nodes returns all nodes."""
        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        results = search_embeddings(query, matrix, top_k=100)
        assert len(results) == 3

    def test_results_sorted_descending(self, matrix: np.ndarray) -> None:
        """Results are sorted by similarity descending."""
        query = np.array([0.6, 0.8, 0.0, 0.0], dtype=np.float32)
        results = search_embeddings(query, matrix, top_k=3)
        sims = [sim for _, sim in results]
        assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# DuckDB concept_embeddings: round-trip persistence
# ---------------------------------------------------------------------------


class TestEmbeddingPersistence:
    """concept_embeddings table: insert, read back, and save/load."""

    def _sample_rows(self) -> list[tuple[str, str, str, str, list[float], str]]:
        """Two synthetic embedding rows with 768-D vectors (matching schema)."""
        rng = np.random.default_rng(42)
        vec_a = rng.standard_normal(768).astype(np.float32).tolist()
        vec_b = rng.standard_normal(768).astype(np.float32).tolist()
        return [
            ("concept:a", "Alpha", "First concept", "concept", vec_a, "measurement"),
            ("concept:b", "Beta", "Second concept", "archetype", vec_b, "measurement"),
        ]

    def test_insert_and_read(self) -> None:
        """Insert embeddings and read them back."""
        store = DuckDBStore.create_empty()
        rows = self._sample_rows()
        store.load_concept_embeddings_batch(rows)

        result = store.get_concept_embeddings()
        assert len(result) == 2
        ids = {r[0] for r in result}
        assert ids == {"concept:a", "concept:b"}
        # Verify embedding dimensions round-trip
        alpha = next(r for r in result if r[0] == "concept:a")
        assert len(alpha[4]) == 768

    def test_empty_batch(self) -> None:
        """Empty batch inserts nothing; read returns empty."""
        store = DuckDBStore.create_empty()
        store.load_concept_embeddings_batch([])
        assert store.get_concept_embeddings() == []

    def test_save_load_roundtrip(self, tmp_path) -> None:
        """Embeddings survive save_to_file / load_from_file."""
        store = DuckDBStore.create_empty()
        store.load_concept_embeddings_batch(self._sample_rows())
        store.finalize()

        db_file = tmp_path / "test.duckdb"
        store.save_to_file(db_file)

        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.get_concept_embeddings()
        assert len(result) == 2
        beta = next(r for r in result if r[0] == "concept:b")
        assert beta[1] == "Beta"
        assert beta[3] == "archetype"
        assert beta[5] == "measurement"

    def test_empty_table_returns_empty(self, tmp_path) -> None:
        """A store with no embeddings inserted returns an empty list."""
        store = DuckDBStore.create_empty()
        store.finalize()
        db_file = tmp_path / "empty.duckdb"
        store.save_to_file(db_file)

        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.get_concept_embeddings()
        assert result == []

    def test_facet_column_roundtrip(self) -> None:
        """Facet column round-trips through insert and read."""
        store = DuckDBStore.create_empty()
        rng = np.random.default_rng(99)
        vec = rng.standard_normal(768).astype(np.float32).tolist()
        rows = [
            ("m:a", "Meas A", "desc", "concept", vec, "measurement"),
            ("f:a", "Focus A", "", "focus", vec, "focus"),
        ]
        store.load_concept_embeddings_batch(rows)
        result = store.get_concept_embeddings()
        facets = {r[0]: r[5] for r in result}
        assert facets == {"f:a": "focus", "m:a": "measurement"}

    def test_old_cache_missing_table(self, tmp_path) -> None:
        """Simulates a pre-embeddings cache file missing the table entirely."""
        import duckdb

        db_file = tmp_path / "old.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE studies (db_gap_id VARCHAR PRIMARY KEY, raw_json VARCHAR)")
        conn.close()

        conn = duckdb.connect(str(db_file), read_only=True)
        with pytest.raises(duckdb.CatalogException):
            conn.execute("SELECT * FROM concept_embeddings")
        conn.close()


# ---------------------------------------------------------------------------
# Facet-filtered embedding search (ConceptIndex level)
# ---------------------------------------------------------------------------


class TestFacetFilteredSearch:
    """Verify that facet filtering returns only nodes of the requested facet."""

    def test_facet_filter_focus_only(self) -> None:
        """Facet='focus' excludes measurement nodes from results."""
        from concept_search.index import ConceptIndex
        from concept_search.models import ConceptMatch, Facet

        idx = ConceptIndex()
        # Populate focus index with a term so study_count lookup works
        idx._index[Facet.FOCUS]["heart failure"] = ConceptMatch(
            facet=Facet.FOCUS, study_count=42, value="Heart Failure"
        )
        # Build synthetic embedding nodes: one measurement, one focus
        idx._embedding_nodes = [
            {"concept_id": "topmed:bp_systolic", "name": "Systolic BP",
             "description": "Systolic blood pressure", "type": "concept",
             "facet": "measurement"},
            {"concept_id": "Heart Failure", "name": "Heart Failure",
             "description": "", "type": "focus", "facet": "focus"},
        ]
        # Two unit vectors: [1,0,0,0] and [0,1,0,0]
        idx._embedding_matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float32)

        # Mock embed_query to return a vector that matches both equally
        import concept_search.embeddings as emb_mod
        original = getattr(emb_mod, "embed_query", None)
        emb_mod.embed_query = lambda q: np.array(
            [0.7, 0.7, 0.0, 0.0], dtype=np.float32
        )
        try:
            results = idx.search_concepts_by_embedding(
                "heart", top_k=10, facet="focus"
            )
            assert len(results) == 1
            assert results[0]["concept_id"] == "Heart Failure"
            assert results[0]["study_count"] == 42
        finally:
            if original is not None:
                emb_mod.embed_query = original

    def test_embedding_cache_hit(self, tmp_path, monkeypatch) -> None:
        """Cached .npy + matching hash skips embed_texts entirely."""
        import hashlib
        from unittest.mock import patch

        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        # Minimal concept description so there's at least one node
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        # Point embedding cache dir at tmp_path
        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        # Pre-populate cache with a matching hash and fake .npy
        texts = ["BP: Blood pressure"]  # matches what _build would produce
        text_hash = hashlib.sha256("\n".join(texts).encode()).hexdigest()
        fake_matrix = np.random.default_rng(0).standard_normal((1, 768)).astype(np.float32)
        np.save(tmp_path / "concept-embeddings.npy", fake_matrix)
        (tmp_path / "concept-embeddings.sha256").write_text(text_hash + "\n")

        # embed_texts should NOT be called — cache hit
        with patch("concept_search.embeddings.embed_texts") as mock_embed:
            idx._build_concept_embeddings()
            mock_embed.assert_not_called()

        assert idx._embedding_matrix is not None
        assert idx._embedding_matrix.shape == (1, 768)

    def test_embedding_cache_miss(self, tmp_path, monkeypatch) -> None:
        """Stale hash triggers recomputation via embed_texts."""
        from unittest.mock import patch

        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        # Write a stale hash
        (tmp_path / "concept-embeddings.sha256").write_text("stale_hash\n")
        np.save(tmp_path / "concept-embeddings.npy", np.zeros((1, 768), dtype=np.float32))

        fake_result = np.ones((1, 768), dtype=np.float32)
        with patch("concept_search.embeddings.embed_texts", return_value=fake_result) as mock_embed:
            idx._build_concept_embeddings()
            # Stale hash should trigger recomputation
            mock_embed.assert_called_once()

        assert idx._embedding_matrix is not None
        np.testing.assert_array_equal(idx._embedding_matrix, fake_result)

    def test_no_facet_returns_all(self) -> None:
        """No facet filter returns nodes of all facets."""
        from concept_search.index import ConceptIndex
        from concept_search.models import Facet

        idx = ConceptIndex()
        idx._embedding_nodes = [
            {"concept_id": "m:a", "name": "A", "description": "",
             "type": "concept", "facet": "measurement"},
            {"concept_id": "f:a", "name": "B", "description": "",
             "type": "focus", "facet": "focus"},
        ]
        idx._embedding_matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float32)

        import concept_search.embeddings as emb_mod
        original = getattr(emb_mod, "embed_query", None)
        emb_mod.embed_query = lambda q: np.array(
            [0.7, 0.7, 0.0, 0.0], dtype=np.float32
        )
        try:
            results = idx.search_concepts_by_embedding("test", top_k=10)
            assert len(results) == 2
        finally:
            if original is not None:
                emb_mod.embed_query = original
