FROM python:3.13-slim

ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

WORKDIR /app

# Install uv for fast, deterministic dependency installs
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

# Install dependencies (layer caching: only re-runs when deps change)
# 1. Export locked deps to requirements.txt
# 2. Strip CUDA-only packages (nvidia-*, triton, cuda-*) — not needed on
#    CPU-only App Runner instances, saves ~3 GB
# 3. Install CPU-only PyTorch from pytorch.org/whl/cpu
# 4. Install remaining deps from PyPI
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv venv .venv && \
    uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt && \
    grep -v -E '^(nvidia-|triton==|cuda-|torch==)' requirements.txt > requirements-cpu.txt && \
    uv pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --no-cache-dir -r requirements-cpu.txt && \
    rm requirements.txt requirements-cpu.txt

# Pre-download embedding model so it's cached in the image.
# Needed at runtime for query embedding (not for batch generation —
# pre-computed embeddings are copied below).
RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO')"

# Copy application code
COPY backend/concept_search/ concept_search/

# Copy files needed at runtime (ISA drill-down, concept descriptions, consent logic).
# Study metadata, demographics, and llm-concepts are baked into the DuckDB cache.
COPY catalog-build/classification/output/concept-isa.json catalog-build/classification/output/concept-isa.json
COPY catalog-build/classification/output/concept-vocabulary.json catalog-build/classification/output/concept-vocabulary.json
COPY catalog-build/classification/output/phenx-concept-vocabulary.json catalog-build/classification/output/phenx-concept-vocabulary.json
COPY catalog-build/classification/output/ncpi-categories.json catalog-build/classification/output/ncpi-categories.json
COPY catalog-build/common/disease_abbrev_mapping.tsv /catalog-build/common/disease_abbrev_mapping.tsv

# Copy pre-built DuckDB cache (built locally via `make db-reload`).
# This eliminates all JSON parsing and embedding generation from the
# Docker build — the container starts with a ready-to-use index.
RUN mkdir -p /cache
COPY catalog/concept-search.duckdb /cache/concept-search.duckdb
ENV NCPI_DUCKDB_CACHE_PATH=/cache/concept-search.duckdb
ENV NCPI_REPO_ROOT=/app

EXPOSE 8000

CMD [".venv/bin/uvicorn", "concept_search.api:app", "--host", "0.0.0.0", "--port", "8000"]
