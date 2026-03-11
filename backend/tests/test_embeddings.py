"""Unit tests for embedding utilities and .npy loading.

Covers search_embeddings edge cases and _load_concept_embeddings_from_npy.
No real model loading — uses synthetic vectors.
"""

from __future__ import annotations

import numpy as np
import pytest

from concept_search.embeddings import search_embeddings

# ---------------------------------------------------------------------------
# search_embeddings: edge cases
# ---------------------------------------------------------------------------


class TestSearchEmbeddings:
    """Edge-case tests for cosine KNN search."""

    @pytest.fixture
    def matrix(self) -> np.ndarray:
        """3 unit vectors in 4-D for easy manual verification."""
        vecs = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
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
            {
                "concept_id": "topmed:bp_systolic",
                "name": "Systolic BP",
                "description": "Systolic blood pressure",
                "type": "concept",
                "facet": "measurement",
            },
            {
                "concept_id": "Heart Failure",
                "name": "Heart Failure",
                "description": "",
                "type": "focus",
                "facet": "focus",
            },
        ]
        # Two unit vectors: [1,0,0,0] and [0,1,0,0]
        idx._embedding_matrix = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )

        # Mock embed_query to return a vector that matches both equally
        import concept_search.embeddings as emb_mod

        original = getattr(emb_mod, "embed_query", None)
        emb_mod.embed_query = lambda q: np.array([0.7, 0.7, 0.0, 0.0], dtype=np.float32)
        try:
            results = idx.search_concepts_by_embedding("heart", top_k=10, facet="focus")
            assert len(results) == 1
            assert results[0]["concept_id"] == "Heart Failure"
            assert results[0]["study_count"] == 42
        finally:
            if original is not None:
                emb_mod.embed_query = original

    def test_load_from_npy(self, tmp_path, monkeypatch) -> None:
        """_load_concept_embeddings_from_npy loads matrix from .npy file."""
        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        fake_matrix = np.random.default_rng(0).standard_normal((1, 768)).astype(np.float32)
        np.save(tmp_path / "concept-embeddings.npy", fake_matrix)

        idx._load_concept_embeddings_from_npy()

        assert idx._embedding_matrix is not None
        assert idx._embedding_matrix.shape == (1, 768)

    def test_load_from_npy_missing_file(self, tmp_path, monkeypatch) -> None:
        """Missing .npy raises FileNotFoundError."""
        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        with pytest.raises(FileNotFoundError, match="make embeddings"):
            idx._load_concept_embeddings_from_npy()

    def test_load_from_npy_row_mismatch(self, tmp_path, monkeypatch) -> None:
        """Row count mismatch between .npy and node list raises ValueError."""
        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        # Save matrix with wrong number of rows
        wrong_matrix = np.zeros((5, 768), dtype=np.float32)
        np.save(tmp_path / "concept-embeddings.npy", wrong_matrix)

        with pytest.raises(ValueError, match="make embeddings"):
            idx._load_concept_embeddings_from_npy()

    def test_load_from_npy_hash_mismatch(self, tmp_path, monkeypatch) -> None:
        """Content hash mismatch raises ValueError."""
        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._concept_descriptions = {
            "topmed:bp": {"description": "Blood pressure", "name": "BP"},
        }

        monkeypatch.setenv("NCPI_EMBEDDING_CACHE_DIR", str(tmp_path))

        fake_matrix = np.random.default_rng(0).standard_normal((1, 768)).astype(np.float32)
        np.save(tmp_path / "concept-embeddings.npy", fake_matrix)
        (tmp_path / "concept-embeddings.sha256").write_text("deadbeef\n")

        with pytest.raises(ValueError, match="hash mismatch"):
            idx._load_concept_embeddings_from_npy()

    def test_no_facet_returns_all(self) -> None:
        """No facet filter returns nodes of all facets."""
        from concept_search.index import ConceptIndex

        idx = ConceptIndex()
        idx._embedding_nodes = [
            {
                "concept_id": "m:a",
                "name": "A",
                "description": "",
                "type": "concept",
                "facet": "measurement",
            },
            {
                "concept_id": "f:a",
                "name": "B",
                "description": "",
                "type": "focus",
                "facet": "focus",
            },
        ]
        idx._embedding_matrix = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )

        import concept_search.embeddings as emb_mod

        original = getattr(emb_mod, "embed_query", None)
        emb_mod.embed_query = lambda q: np.array([0.7, 0.7, 0.0, 0.0], dtype=np.float32)
        try:
            results = idx.search_concepts_by_embedding("test", top_k=10)
            assert len(results) == 2
        finally:
            if original is not None:
                emb_mod.embed_query = original
