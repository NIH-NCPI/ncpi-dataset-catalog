FROM python:3.13-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY concept_search/ concept_search/

EXPOSE 8000

CMD ["uvicorn", "concept_search.api:app", "--host", "0.0.0.0", "--port", "8000"]
