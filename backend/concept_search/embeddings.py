"""Embedding utilities for semantic concept search.

Wraps ``sentence-transformers`` to provide lazy model loading,
batch encoding, and cosine KNN search against concept embeddings.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
_model = None
_model_lock = threading.Lock()


def get_model():
    """Lazy-load S-PubMedBert-MS-MARCO (cached after first call).

    Thread-safe: uses a lock to prevent concurrent initialization
    (which can trigger PyTorch meta-tensor errors).

    Returns:
        A ``SentenceTransformer`` instance.
    """
    global _model  # noqa: PLW0603
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model: %s", _MODEL_NAME)
                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("Embedding model loaded")
    return _model


def embed_texts(texts: list[str], batch_size: int = 256) -> np.ndarray:
    """Encode a batch of texts into normalized embeddings.

    Args:
        texts: Strings to encode.
        batch_size: Batch size for encoding.

    Returns:
        (N, 768) float32 array, L2-normalized.
    """
    model = get_model()
    vecs = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
    vecs = vecs.astype(np.float32)
    # L2-normalize for cosine similarity via dot product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def embed_query(query: str) -> np.ndarray:
    """Encode a single query into a normalized embedding.

    Args:
        query: Query string.

    Returns:
        (768,) float32 array, L2-normalized.
    """
    model = get_model()
    vec = model.encode(query, show_progress_bar=False).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def search_embeddings(
    query_vec: np.ndarray,
    node_vecs: np.ndarray,
    top_k: int = 10,
) -> list[tuple[int, float]]:
    """Cosine KNN: find the top-K most similar nodes.

    Both ``query_vec`` and ``node_vecs`` must be L2-normalized.

    Args:
        query_vec: (768,) normalized query vector.
        node_vecs: (N, 768) normalized node matrix.
        top_k: Number of results to return.

    Returns:
        List of ``(index, similarity)`` tuples, sorted descending.
    """
    # Dot product on normalized vectors = cosine similarity
    similarities = node_vecs @ query_vec
    if top_k <= 0 or len(similarities) == 0:
        return []
    top_k = min(top_k, len(similarities))
    top_indices = np.argpartition(similarities, -top_k)[-top_k:]
    top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
    return [(int(idx), float(similarities[idx])) for idx in top_indices]
