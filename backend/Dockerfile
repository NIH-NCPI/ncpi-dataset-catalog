FROM python:3.13-slim

ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

WORKDIR /app

# Install dependencies first (layer caching: only re-runs when deps change)
COPY backend/pyproject.toml .
RUN pip install --no-cache-dir \
    $(python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(' '.join(d['project']['dependencies']))")

# Copy application code
COPY backend/concept_search/ concept_search/

# Copy catalog data (built by npm run build-ncpi-db)
COPY catalog/ncpi-platform-studies.json catalog/ncpi-platform-studies.json
COPY catalog-build/classification/output/llm-concepts-v4/ catalog-build/classification/output/llm-concepts-v4/
COPY catalog-build/classification/output/concept-isa.json catalog-build/classification/output/concept-isa.json
COPY catalog-build/classification/output/demographic-profiles.json catalog-build/classification/output/demographic-profiles.json

# Writable directory for DuckDB cache
RUN mkdir -p /cache
ENV NCPI_DUCKDB_CACHE_PATH=/cache/concept-search.duckdb
ENV NCPI_REPO_ROOT=/app

EXPOSE 8000

CMD ["uvicorn", "concept_search.api:app", "--host", "0.0.0.0", "--port", "8000"]
