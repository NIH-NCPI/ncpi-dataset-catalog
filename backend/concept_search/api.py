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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api_models import (
    DemographicCategory,
    DemographicDistribution,
    SearchRequest,
    SearchResponse,
    SearchTiming,
    StudyDemographics,
    StudySummary,
    VariableResult,
)
from .index import get_index
from .models import (
    Facet,
    QueryModel,
    ResolvedMention,
    RouteAdd,
    RouteRemove,
    RouteReplace,
    RouteReset,
    RouteSelect,
)
from .pipeline import pipeline_cache, run_pipeline
from .rate_limit import RateLimiter
from .resolve_agent import resolve_cache
from .router_agent import run_router

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


async def _cleanup_rate_limiter() -> None:
    """Periodically purge expired rate-limit entries."""
    while True:
        await asyncio.sleep(300)
        await _rate_limiter.cleanup()


def _get_client_ip(fastapi_request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For from App Runner."""
    forwarded = fastapi_request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = fastapi_request.client
    return client.host if client else "unknown"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Preload the ConceptIndex at startup."""
    _log_json(event="index_loading")
    t0 = time.monotonic()
    get_index()
    elapsed = time.monotonic() - t0
    _log_json(event="index_loaded", elapsed_s=round(elapsed, 1))
    # Eagerly load the embedding model so the first request isn't slow.
    # If this fails (e.g. missing weights), log and continue — keyword
    # search still works without embeddings.
    try:
        from .embeddings import get_model
        get_model()
    except Exception:
        logger.exception("Failed to preload embedding model at startup")
    cleanup_task = asyncio.create_task(_cleanup_rate_limiter())
    try:
        yield
    finally:
        cleanup_task.cancel()


app = FastAPI(title="NCPI Concept Search API", lifespan=lifespan)

# Limit concurrent LLM pipeline calls to cap Anthropic API costs.
_pipeline_semaphore = asyncio.Semaphore(5)

# Per-IP rate limiter (env-configurable, defaults 10 req / 60 s).
_rate_limiter = RateLimiter()

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
    allow_headers=["Content-Type"],
    allow_methods=["GET", "POST"],
    allow_origins=_cors_origins,
)


def _build_distribution(raw: dict) -> DemographicDistribution:
    """Convert a raw demographics dimension dict to a model."""
    return DemographicDistribution(
        categories=[
            DemographicCategory(
                count=c.get("count", 0),
                label=c.get("label", ""),
                percent=c.get("percent", 0.0),
            )
            for c in raw.get("categories", [])
        ],
        n=raw.get("n", 0),
    )


def _build_demographics(study: dict) -> StudyDemographics | None:
    """Build StudyDemographics from a study's ``demographics`` dict."""
    demo = study.get("demographics")
    if not demo:
        return None
    return StudyDemographics(
        computed_ancestry=_build_distribution(demo["computedAncestry"])
        if demo.get("computedAncestry")
        else None,
        race_ethnicity=_build_distribution(demo["raceEthnicity"])
        if demo.get("raceEthnicity")
        else None,
        sex=_build_distribution(demo["sex"]) if demo.get("sex") else None,
    )


def _build_study_summary(study: dict) -> StudySummary:
    """Project a full study dict into a lean StudySummary."""
    return StudySummary(
        consent_codes=study.get("consentCodes", []),
        data_types=study.get("dataTypes", []),
        db_gap_id=study.get("dbGapId", ""),
        demographics=_build_demographics(study),
        focus=study.get("focus"),
        participant_count=study.get("participantCount"),
        platforms=study.get("platforms", []),
        study_designs=study.get("studyDesigns", []),
        title=study.get("title", ""),
    )


def _build_dbgap_variable_url(study_accession: str, phv_id: str) -> str:
    """Build a dbGaP URL for a specific variable.

    Args:
        study_accession: Versioned study accession (e.g., "phs000007.v1.p1").
        phv_id: Variable PHV ID (e.g., "phv00481718.v2.p1").

    Returns:
        Full URL to the variable page on dbGaP, or empty string if missing.
    """
    if not phv_id or not study_accession:
        return ""
    phv_num = phv_id.split(".")[0].replace("phv", "")
    return (
        "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi"
        f"?study_id={study_accession}&phv={phv_num}"
    )


def _build_dbgap_study_url(study_id: str) -> str:
    """Build a dbGaP study page URL.

    Args:
        study_id: Study accession (e.g., "phs000007").

    Returns:
        Full URL to the study page on dbGaP.
    """
    return f"https://dbgap.ncbi.nlm.nih.gov/study/{study_id}"


def _build_variable_result(row: dict) -> VariableResult:
    """Convert a raw variable dict from the store into a VariableResult."""
    study_id = row.get("studyId", "")
    study_accession = row.get("studyAccession", "")
    concept_id = row.get("concept", "")
    # Derive display name from namespaced concept_id
    display = concept_id.split(":", 1)[-1] if concept_id else ""
    return VariableResult(
        concept=display,
        concept_id=concept_id,
        cui=row.get("cui") or None,
        dataset_id=row.get("datasetId", ""),
        db_gap_url=_build_dbgap_variable_url(
            study_accession, row.get("phvId", "")
        ),
        description=row.get("description", ""),
        phv_id=row.get("phvId", ""),
        study_id=study_id,
        study_title=row.get("studyTitle", ""),
        study_url=_build_dbgap_study_url(study_id),
        table_name=row.get("tableName", ""),
        variable_name=row.get("variableName", ""),
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


async def _handle_route(
    query: str, previous_query: QueryModel | None
) -> QueryModel:
    """Route a follow-up message through the router agent and dispatch.

    Args:
        query: The user's follow-up message.
        previous_query: Previous query state with active filters.

    Returns:
        Updated QueryModel after applying the routed action.
    """
    assert previous_query is not None
    route = await run_router(query, previous_query)
    logger.info("Router: %s", route.kind)

    if isinstance(route, RouteSelect):
        # Set values from selected disambiguation concept_ids, clear disambiguation
        mentions = []
        for m in previous_query.mentions:
            if m.disambiguation and any(
                opt.concept_id in route.selected_ids
                for opt in m.disambiguation
            ):
                mentions.append(
                    ResolvedMention(
                        facet=m.facet,
                        original_text=m.original_text,
                        values=route.selected_ids,
                    )
                )
            else:
                mentions.append(m)
        return QueryModel(
            intent=previous_query.intent,
            mentions=mentions,
        )

    if isinstance(route, RouteRemove):
        # Drop matching mentions
        remove_set = {t.lower() for t in route.original_texts}
        mentions = [
            m for m in previous_query.mentions
            if m.original_text.lower() not in remove_set
        ]
        return QueryModel(
            intent=previous_query.intent,
            mentions=mentions,
            message="OK, removed." if not mentions else None,
        )

    if isinstance(route, RouteReplace):
        # Drop the old mention, run pipeline on new text with remaining mentions
        remaining = [
            m for m in previous_query.mentions
            if m.original_text.lower() != route.original_text.lower()
        ]
        modified_previous = QueryModel(
            intent=previous_query.intent,
            mentions=remaining,
        )
        return await run_pipeline(
            route.new_text, previous_query=modified_previous
        )

    if isinstance(route, RouteReset):
        # Fresh pipeline, ignore previous state
        return await run_pipeline(route.new_query)

    # RouteAdd — fall through to existing refine pipeline
    return await run_pipeline(query, previous_query=previous_query)


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, fastapi_request: Request
) -> SearchResponse | JSONResponse:
    """Run the concept search pipeline and return matching studies."""
    # 1. Rate limit check
    client_ip = _get_client_ip(fastapi_request)
    if not await _rate_limiter.is_allowed(client_ip):
        _log_json(event="rate_limited", ip=client_ip, query=request.query)
        return JSONResponse(
            content={"detail": "Too many requests — please try again later."},
            status_code=429,
        )

    has_query = bool(request.query and request.query.strip())
    has_previous = request.previous_query is not None
    if has_query and has_previous:
        mode = "route"
    elif has_previous:
        mode = "requery"
    else:
        mode = "fresh"

    _log_json(event="search_request", mode=mode, query=request.query)
    t_start = time.monotonic()

    if mode == "requery":
        # Requery: skip LLM pipeline entirely, use previous query as-is.
        assert request.previous_query is not None
        query_model = request.previous_query
        t_pipeline = t_start  # No pipeline work — zero out pipeline_ms.
    else:
        try:
            async with _pipeline_semaphore:
                if mode == "route":
                    query_model = await asyncio.wait_for(
                        _handle_route(request.query, request.previous_query),
                        timeout=60.0,
                    )
                else:
                    query_model = await asyncio.wait_for(
                        run_pipeline(request.query),
                        timeout=60.0,
                    )
        except (TimeoutError, asyncio.CancelledError):
            _log_json(event="search_timeout", query=request.query)
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            return SearchResponse(
                message="Search timed out — please try a simpler query.",
                query=QueryModel(mentions=[]),
                studies=[],
                timing=SearchTiming(
                    lookup_ms=0,
                    pipeline_ms=elapsed_ms,
                    total_ms=elapsed_ms,
                ),
                total_studies=0,
            )
        except Exception as exc:
            _log_json(
                event="search_pipeline_error",
                query=request.query,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            return SearchResponse(
                message="Something went wrong — please try again.",
                query=QueryModel(mentions=[]),
                studies=[],
                timing=SearchTiming(
                    lookup_ms=0,
                    pipeline_ms=elapsed_ms,
                    total_ms=elapsed_ms,
                ),
                total_studies=0,
            )
        t_pipeline = time.monotonic()

    # Deterministic lookup — branch on intent
    index = get_index()
    intent = query_model.intent
    studies: list[dict] = []
    variable_rows: list[dict] = []
    total_variable_count = 0

    if query_model.mentions:
        include, exclude = _split_mentions(query_model.mentions)
        if intent == "auto":
            pass  # Ambiguous — return clarification message only
        elif intent == "variable":
            # Apply study-level constraints (platform, dataType, etc.)
            non_measurement = [
                c for c in include if c[0] != Facet.MEASUREMENT
            ]
            study_ids: set[str] | None = None
            if non_measurement:
                matched = index.query_studies(
                    non_measurement, exclude or None
                )
                study_ids = {s.get("dbGapId", "") for s in matched}
            elif exclude:
                matched = index.query_studies([], exclude)
                study_ids = {s.get("dbGapId", "") for s in matched}

            # Collect all measurement concepts and query variables
            # via ISA closure (matched_variables are kept for display
            # but not used as a SQL filter — the concept tag is enough).
            all_concepts: list[str] = []
            for m in query_model.mentions:
                if m.facet != Facet.MEASUREMENT or m.exclude:
                    continue
                all_concepts.extend(m.values)

            if all_concepts or study_ids:
                rows, total_variable_count = (
                    index.store.query_variables(
                        concepts=all_concepts or None,
                        study_ids=study_ids,
                    )
                )
                variable_rows.extend(rows)
        else:
            studies = index.query_studies(include, exclude or None)

    t_lookup = time.monotonic()

    pipeline_ms = int((t_pipeline - t_start) * 1000)
    lookup_ms = int((t_lookup - t_pipeline) * 1000)

    response = SearchResponse(
        intent=intent,
        message=query_model.message,
        query=query_model,
        studies=[_build_study_summary(s) for s in studies],
        timing=SearchTiming(
            lookup_ms=lookup_ms,
            pipeline_ms=pipeline_ms,
            total_ms=pipeline_ms + lookup_ms,
        ),
        total_studies=len(studies),
        total_variables=total_variable_count,
        variables=[_build_variable_result(r) for r in variable_rows],
    )

    _log_json(
        event="search_response",
        intent=intent,
        mode=mode,
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
        total_variables=len(variable_rows),
        pipeline_ms=pipeline_ms,
        lookup_ms=lookup_ms,
    )

    return response


@app.get("/health")
async def health() -> dict:
    """Return service health and index statistics."""
    index = get_index()
    return {
        "gitSha": os.environ.get("GIT_SHA", "unknown"),
        "indexStats": index.stats,
        "pipelineCache": pipeline_cache.stats,
        "resolveCache": resolve_cache.stats,
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
