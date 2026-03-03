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

    def _sample_rows(self) -> list[tuple[str, str, str, str, list[float]]]:
        """Two synthetic embedding rows with 768-D vectors (matching schema)."""
        rng = np.random.default_rng(42)
        vec_a = rng.standard_normal(768).astype(np.float32).tolist()
        vec_b = rng.standard_normal(768).astype(np.float32).tolist()
        return [
            ("concept:a", "Alpha", "First concept", "concept", vec_a),
            ("concept:b", "Beta", "Second concept", "archetype", vec_b),
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

    def test_empty_table_returns_empty(self, tmp_path) -> None:
        """A store with no embeddings inserted returns an empty list."""
        store = DuckDBStore.create_empty()
        store.finalize()
        db_file = tmp_path / "empty.duckdb"
        store.save_to_file(db_file)

        loaded = DuckDBStore.load_from_file(db_file)
        result = loaded.get_concept_embeddings()
        assert result == []

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
