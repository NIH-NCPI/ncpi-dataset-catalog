"""FastAPI application for the NCPI Concept Search API."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api_models import SearchRequest, SearchResponse, SearchTiming, StudySummary
from .index import get_index
from .models import Facet
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

# Load .env from the backend directory (parent of this package)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Preload the ConceptIndex at startup."""
    logger.info("Preloading ConceptIndex...")
    t0 = time.monotonic()
    get_index()
    elapsed = time.monotonic() - t0
    logger.info("ConceptIndex loaded in %.1fs", elapsed)
    yield


app = FastAPI(title="NCPI Concept Search API", lifespan=lifespan)

# CORS — allow localhost:3000 (dev) plus any origins in CORS_ORIGINS env var
_cors_origins = ["http://localhost:3000"]
_extra = os.environ.get("CORS_ORIGINS", "")
if _extra:
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_headers=["*"],
    allow_methods=["*"],
    allow_origins=_cors_origins,
)


def _build_study_summary(study: dict) -> StudySummary:
    """Project a full study dict into a lean StudySummary."""
    return StudySummary(
        consent_codes=study.get("consentCodes", []),
        data_types=study.get("dataTypes", []),
        db_gap_id=study.get("dbGapId", ""),
        focus=study.get("focus"),
        participant_count=study.get("participantCount"),
        platforms=study.get("platforms", []),
        study_designs=study.get("studyDesigns", []),
        title=study.get("title", ""),
    )


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """Run the concept search pipeline and return matching studies."""
    t_start = time.monotonic()

    # Run the 3-agent LLM pipeline
    query_model = await run_pipeline(request.query)
    t_pipeline = time.monotonic()

    # Deterministic study lookup
    index = get_index()
    studies: list[dict] = []

    if query_model.mentions:
        # Build facet_values from non-excluded mentions
        facet_values: dict[Facet, list[str]] = {}
        for mention in query_model.mentions:
            if mention.exclude:
                continue
            if mention.values:
                facet_values.setdefault(mention.facet, []).extend(mention.values)

        studies = index.get_studies_for_mentions(facet_values)

        # Subtract studies matching excluded mentions
        excluded_facet_values: dict[Facet, list[str]] = {}
        for mention in query_model.mentions:
            if not mention.exclude:
                continue
            if mention.values:
                excluded_facet_values.setdefault(mention.facet, []).extend(
                    mention.values
                )

        if excluded_facet_values:
            excluded_studies = index.get_studies_for_mentions(excluded_facet_values)
            excluded_ids = {s.get("dbGapId") for s in excluded_studies}
            studies = [s for s in studies if s.get("dbGapId") not in excluded_ids]

    t_lookup = time.monotonic()

    pipeline_ms = int((t_pipeline - t_start) * 1000)
    lookup_ms = int((t_lookup - t_pipeline) * 1000)

    return SearchResponse(
        message=query_model.message,
        query=query_model,
        studies=[_build_study_summary(s) for s in studies],
        timing=SearchTiming(
            lookup_ms=lookup_ms,
            pipeline_ms=pipeline_ms,
            total_ms=pipeline_ms + lookup_ms,
        ),
        total_studies=len(studies),
    )


@app.get("/health")
async def health() -> dict:
    """Return service health and index statistics."""
    index = get_index()
    return {
        "indexStats": index.stats,
        "status": "ok",
    }


@app.exception_handler(Exception)
async def global_exception_handler(_request: object, exc: Exception) -> JSONResponse:
    """Return 500 with error detail for unhandled exceptions."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        content={"detail": str(exc)},
        status_code=500,
    )


def main() -> None:
    """Entry point for the concept-search-api script."""
    import uvicorn

    uvicorn.run("concept_search.api:app", host="0.0.0.0", port=8000)
