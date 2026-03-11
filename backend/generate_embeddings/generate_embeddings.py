"""Standalone embedding generator — runs outside the backend venv.

Reads concept descriptions from JSON files and focus terms from the
catalog, then generates the .npy embedding cache using
sentence-transformers (with GPU/Metal torch when available).

Usage:
    cd backend/generate_embeddings && uv run python generate_embeddings.py

The backend's `make db-reload` will pick up the cached .npy file
and skip its own embedding generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def resolve_repo_root() -> Path:
    """Walk up from this script to find the repo root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "catalog").is_dir() and (p / "catalog-build").is_dir():
            return p
        p = p.parent
    sys.exit("Could not find repo root (expected catalog/ and catalog-build/ dirs)")


def load_concept_descriptions(repo_root: Path) -> dict[str, dict]:
    """Load concept descriptions from vocabulary JSON files."""
    vocab_dir = repo_root / "catalog-build" / "classification" / "output"
    isa_path = vocab_dir / "concept-isa.json"

    descriptions: dict[str, dict] = {}

    # Build known namespaced IDs from ISA table
    known_ids: set[str] = set()
    if isa_path.exists():
        with open(isa_path) as f:
            for entry in json.load(f):
                known_ids.add(entry["child"])
                known_ids.add(entry["parent"])

    # TOPMed concepts
    topmed_path = vocab_dir / "concept-vocabulary.json"
    if topmed_path.exists():
        with open(topmed_path) as f:
            for entry in json.load(f):
                bare = entry.get("concept_id", "")
                if ":" in bare:
                    cid = bare
                else:
                    candidates = [k for k in known_ids if k.endswith(f":{bare}")]
                    cid = candidates[0] if len(candidates) == 1 else f"topmed:{bare}"
                desc_entry: dict[str, str] = {
                    "description": entry.get("description", ""),
                    "name": entry.get("name", cid),
                }
                if entry.get("type"):
                    desc_entry["type"] = entry["type"]
                descriptions[cid] = desc_entry

    # PhenX concepts
    phenx_path = vocab_dir / "phenx-concept-vocabulary.json"
    if phenx_path.exists():
        with open(phenx_path) as f:
            for entry in json.load(f):
                cid = entry.get("concept_id", "")
                descriptions[cid] = {
                    "description": entry.get("description", ""),
                    "name": entry.get("name", cid),
                }

    # NCPI categories
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


def load_focus_terms(repo_root: Path) -> list[str]:
    """Load unique focus terms from ncpi-platform-studies.json."""
    studies_path = repo_root / "catalog" / "ncpi-platform-studies.json"
    if not studies_path.exists():
        logger.warning("Studies file not found at %s", studies_path)
        return []

    with open(studies_path) as f:
        studies = json.load(f)

    terms: set[str] = set()
    for study in studies.values():
        focus = study.get("focus")
        if focus:
            terms.add(focus)
    # Sort by lowercased term to match backend index ordering
    # (index.py sorts self._index[Facet.FOCUS].items() by key, which is value.lower())
    return sorted(terms, key=str.lower)


def main() -> None:
    repo_root = resolve_repo_root()
    cache_dir = repo_root / "catalog-build" / "classification" / "output"
    npy_path = cache_dir / "concept-embeddings.npy"
    hash_path = cache_dir / "concept-embeddings.sha256"

    # Build node list (same order as backend's _build_concept_embeddings)
    descs = load_concept_descriptions(repo_root)
    focus_terms = load_focus_terms(repo_root)

    nodes: list[dict] = []
    texts: list[str] = []

    # Measurement nodes
    for cid, info in sorted(descs.items()):
        name = info.get("name", cid)
        desc = info.get("description", "")
        nodes.append({"concept_id": cid, "facet": "measurement", "name": name})
        texts.append(f"{name}: {desc}" if desc else name)

    # Focus nodes
    for term in focus_terms:
        nodes.append({"concept_id": term, "facet": "focus", "name": term})
        texts.append(term)

    if not texts:
        sys.exit("No concepts or focus terms found — nothing to embed")

    # Check content hash
    text_hash = hashlib.sha256("\n".join(texts).encode()).hexdigest()
    if npy_path.exists() and hash_path.exists():
        cached_hash = hash_path.read_text().splitlines()[0].strip()
        if cached_hash == text_hash:
            matrix = np.load(npy_path, allow_pickle=False)
            if matrix.shape == (len(nodes), 768):
                logger.info("Embeddings already up to date (%d nodes) — nothing to do", len(nodes))
                return

    logger.info("Generating embeddings for %d nodes (%d measurement, %d focus)...",
                len(nodes), len(descs), len(focus_terms))

    import torch
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s (torch %s)", device, torch.__version__)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("pritamdeka/S-PubMedBert-MS-MARCO", device=device)

    t0 = time.time()
    vecs = model.encode(texts, batch_size=256, show_progress_bar=True)
    vecs = vecs.astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = vecs / norms
    elapsed = time.time() - t0

    logger.info("Embedding complete: %s in %.1fs", matrix.shape, elapsed)

    # Atomic write
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_npy = npy_path.with_suffix(".npy.tmp")
    tmp_hash = hash_path.with_suffix(".sha256.tmp")
    with open(tmp_npy, "wb") as f:
        np.save(f, matrix)
    meta = f"{text_hash}\ndevice={device} torch={torch.__version__}\n"
    tmp_hash.write_text(meta)
    os.replace(tmp_npy, npy_path)
    os.replace(tmp_hash, hash_path)

    logger.info("Saved: %s", npy_path)


if __name__ == "__main__":
    main()
