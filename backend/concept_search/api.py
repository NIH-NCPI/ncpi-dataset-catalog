"""FastAPI application for the NCPI Concept Search API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
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
from .models import Facet, QueryModel, ResolvedMention
from .pipeline import run_pipeline

# Structured JSON logging to stdout (picked up by CloudWatch via App Runner)
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _log_json(**kwargs: object) -> None:
    """Emit a structured JSON log line."""
    logger.info(json.dumps(kwargs, default=str))


# Load .env from the backend directory (parent of this package)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Preload the ConceptIndex at startup."""
    _log_json(event="index_loading")
    t0 = time.monotonic()
    get_index()
    elapsed = time.monotonic() - t0
    _log_json(event="index_loaded", elapsed_s=round(elapsed, 1))
    yield


app = FastAPI(title="NCPI Concept Search API", lifespan=lifespan)

# CORS — allow known origins plus any extras in CORS_ORIGINS env var
_cors_origins = [
    "http://localhost:3000",
    "https://ncpi-data.dev.clevercanary.com",
    "https://ncpi-data.org",
]
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


def _split_mentions(
    mentions: list[ResolvedMention],
) -> tuple[list[tuple[Facet, list[str]]], list[tuple[Facet, list[str]]]]:
    """Split mentions into include and exclude constraint lists.

    Each mention becomes its own constraint tuple (AND between mentions,
    OR within a mention's values).
    """
    include: list[tuple[Facet, list[str]]] = []
    exclude: list[tuple[Facet, list[str]]] = []
    for mention in mentions:
        if mention.values:
            target = exclude if mention.exclude else include
            target.append((mention.facet, mention.values))
    return include, exclude


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """Run the concept search pipeline and return matching studies."""
    _log_json(event="search_request", query=request.query)
    t_start = time.monotonic()

    # Run the 3-agent LLM pipeline (timeout guards against hanging LLM calls)
    try:
        query_model = await asyncio.wait_for(
            run_pipeline(request.query), timeout=60.0
        )
    except TimeoutError:
        _log_json(event="search_timeout", query=request.query)
        return SearchResponse(
            message="Search timed out — please try a simpler query.",
            query=QueryModel(mentions=[]),
            studies=[],
            timing=SearchTiming(
                lookup_ms=0,
                pipeline_ms=int((time.monotonic() - t_start) * 1000),
                total_ms=int((time.monotonic() - t_start) * 1000),
            ),
            total_studies=0,
        )
    t_pipeline = time.monotonic()

    # Deterministic study lookup
    index = get_index()
    studies: list[dict] = []

    if query_model.mentions:
        include, exclude = _split_mentions(query_model.mentions)
        studies = index.query_studies(include, exclude or None)

    t_lookup = time.monotonic()

    pipeline_ms = int((t_pipeline - t_start) * 1000)
    lookup_ms = int((t_lookup - t_pipeline) * 1000)

    response = SearchResponse(
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

    _log_json(
        event="search_response",
        query=request.query,
        mentions=[
            {
                "facet": m.facet.value,
                "values": m.values,
                "exclude": m.exclude,
            }
            for m in query_model.mentions
        ],
        message=query_model.message,
        total_studies=len(studies),
        pipeline_ms=pipeline_ms,
        lookup_ms=lookup_ms,
    )

    return response


@app.get("/health")
async def health() -> dict:
    """Return service health and index statistics."""
    index = get_index()
    return {
        "indexStats": index.stats,
        "status": "ok",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: object, exc: Exception) -> JSONResponse:
    """Return 500 with error detail for unhandled exceptions."""
    _log_json(
        event="search_error",
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        content={"detail": "Internal server error"},
        status_code=500,
    )


def main() -> None:
    """Entry point for the concept-search-api script."""
    import uvicorn

    uvicorn.run("concept_search.api:app", host="0.0.0.0", port=8000)
