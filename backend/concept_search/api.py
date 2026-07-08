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
    SearchAgentFilterRequest,
    SearchAgentRequest,
    SearchResponse,
    SearchTiming,
    StudyDemographics,
    StudySummary,
    VariableResult,
)
from .api_models import QueryClause as ApiQueryClause
from .api_models import QueryStructure as ApiQueryStructure
from .conversation_agent import (
    AgentDeps,
    deserialize_history,
    run_conversation,
    serialize_history,
)
from .index import ConceptIndex, get_index
from .models import (
    ConversationMessage,
    Facet,
    QueryModel,
    ResolvedMention,
)
from .rate_limit import RateLimiter
from .resolve_agent import resolve_cache
from .response_summary import (
    QueryStructure,
    build_message,
    build_query_structure,
    diagnose_empty_results,
)
from .search_execution import execute_query_model
from .session_store import SessionState, get_session_store, truncate_history

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


def _to_api_query_structure(query_structure: QueryStructure | None) -> ApiQueryStructure | None:
    """Convert an internal QueryStructure to the API model (or None)."""
    if query_structure is None:
        return None
    return ApiQueryStructure(
        clauses=[
            ApiQueryClause(
                exclude=c.exclude,
                facet=c.facet,
                labels=c.labels,
                operator=c.operator,
            )
            for c in query_structure.clauses
        ],
        intent=query_structure.intent,
        summary=query_structure.summary,
    )


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
        db_gap_url=_build_dbgap_variable_url(study_accession, row.get("phvId", "")),
        description=row.get("description", ""),
        phv_id=row.get("phvId", ""),
        study_id=study_id,
        study_title=row.get("studyTitle", ""),
        study_url=_build_dbgap_study_url(study_id),
        table_name=row.get("tableName", ""),
        variable_name=row.get("variableName", ""),
    )


def _timeout_response(elapsed_ms: int, message: str) -> SearchResponse:
    """Build an empty SearchResponse for a timeout/error on either search path."""
    return SearchResponse(
        message=message,
        query=QueryModel(mentions=[]),
        studies=[],
        timing=SearchTiming(lookup_ms=0, pipeline_ms=elapsed_ms, total_ms=elapsed_ms),
        total_studies=0,
    )


def _build_response_message(
    query_model: QueryModel,
    query_structure: QueryStructure | None,
    studies: list,
    variable_rows: list,
    total_variable_count: int,
    index: ConceptIndex,
) -> str | None:
    """Build the deterministic response message for a lookup result.

    Shared by ``/search`` and ``/search/agent/filter`` (``/search/agent`` uses
    the agent's own reply instead). Also populates ``query_structure.summary``
    as a side effect when it is empty.

    Args:
        query_model: The resolved query model that was executed.
        query_structure: Structured query built from the model (may be None).
        studies: Matched studies from execution.
        variable_rows: Matched variable rows from execution.
        total_variable_count: Total matched variable count.
        index: The concept index (for empty-result diagnosis).

    Returns:
        The message to display, or None when there is nothing to say.
    """
    intent = query_model.intent
    if query_model.message:
        # Disambiguation/removal — keep existing message.
        # Still populate query_structure.summary independently so it
        # always describes the query, not the disambiguation text.
        message = query_model.message
        # Populate summary independently — but skip for intent=="ambiguous"
        # where lookup was skipped and counts would be misleading (0).
        if query_structure is not None and not query_structure.summary and intent != "ambiguous":
            build_message(
                query_structure,
                len(studies),
                total_variable_count,
                query_model,
            )
        return message
    if not studies and not variable_rows and query_model.mentions:
        # Zero results — recovery guidance.
        # Set summary to just the header line (e.g. "No studies found where…").
        message = diagnose_empty_results(query_model, index)
        if query_structure is not None and not query_structure.summary:
            query_structure.summary = message.split("\n", 1)[0]
        return message
    if query_model.mentions:
        # Normal results — build_message sets summary as side effect
        return build_message(
            query_structure,
            len(studies),
            total_variable_count,
            query_model,
        )
    return None


def _remove_filter_value(query: QueryModel, facet: Facet, value: str) -> QueryModel:
    """Drop a single facet value from the query, removing emptied mentions.

    Value-granular to match filter-chip clicks: a mention with several OR-ed
    values keeps the rest; a mention left with no values is dropped entirely.
    Any stale clarification message is cleared — the result reflects a plain
    lookup, not a pending disambiguation.

    Args:
        query: The query model to remove the value from (not mutated).
        facet: Facet of the chip that was removed.
        value: Canonical value of the chip that was removed.

    Returns:
        A new QueryModel without the given facet value.
    """
    mentions: list[ResolvedMention] = []
    for mention in query.mentions:
        if mention.facet != facet:
            mentions.append(mention)
            continue
        values = [v for v in mention.values if v != value]
        if not values:
            continue
        mentions.append(mention.model_copy(update={"values": values}))
    return query.model_copy(update={"mentions": mentions, "message": None})


def _rate_limit_response(client_ip: str, query: str) -> JSONResponse:
    """Log a rate-limit hit and build the 429 response (shared by both search paths)."""
    _log_json(event="rate_limited", ip=client_ip, query=query)
    return JSONResponse(
        content={"detail": "Too many requests — please try again later."},
        status_code=429,
    )


# truncate_history keeps the first message plus the most recent N, so up to N+1
# pydantic-ai messages are sent to the model (and retained in the stored history).
_MAX_AGENT_HISTORY = 40
_MAX_SESSION_MESSAGES = 50  # user/assistant text turns retained in the persisted transcript


@app.post("/search/agent", response_model=SearchResponse)
async def search_agent(
    request: SearchAgentRequest, fastapi_request: Request
) -> SearchResponse | JSONResponse:
    """Agentic multi-turn search (epic #365).

    The orchestrator builds a QueryModel via tools; the backend owns conversation
    state keyed by ``session_id``. Returns the same SearchResponse shape as
    ``/search`` — rows from deterministic execution, ``message`` is the agent's reply.
    """
    client_ip = _get_client_ip(fastapi_request)
    if not await _rate_limiter.is_allowed(client_ip):
        return _rate_limit_response(client_ip, request.query)

    _log_json(event="agent_request", session_id=request.session_id, query=request.query)
    t_start = time.monotonic()

    store = get_session_store()
    try:
        state = await store.get(request.session_id) or SessionState()
    except Exception as exc:  # noqa: BLE001 — a store read failure is retryable, not a 500
        _log_json(
            event="agent_store_error",
            op="get",
            session_id=request.session_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        return _timeout_response(elapsed_ms, "Something went wrong — please try again.")
    index = get_index()
    deps = AgentDeps(
        index=index, query_state=state.query or QueryModel(), pending=list(state.pending)
    )
    history = truncate_history(
        deserialize_history(state.agent_message_history), _MAX_AGENT_HISTORY
    )

    try:
        async with _pipeline_semaphore:
            reply, query_model, new_history = await asyncio.wait_for(
                run_conversation(request.query, deps, message_history=history),
                timeout=60.0,
            )
    except (TimeoutError, asyncio.CancelledError):
        _log_json(event="agent_timeout", session_id=request.session_id, query=request.query)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        return _timeout_response(elapsed_ms, "Search timed out — please try again.")
    except Exception as exc:  # noqa: BLE001 — surface a friendly reply, log the detail
        _log_json(
            event="agent_error",
            session_id=request.session_id,
            query=request.query,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        return _timeout_response(elapsed_ms, "Something went wrong — please try again.")

    t_pipeline = time.monotonic()
    execution = execute_query_model(query_model, index)
    t_lookup = time.monotonic()
    pipeline_ms = int((t_pipeline - t_start) * 1000)
    lookup_ms = int((t_lookup - t_pipeline) * 1000)

    query_structure = build_query_structure(query_model, index)
    response = SearchResponse(
        intent=query_model.intent,
        message=reply,
        query=query_model,
        query_structure=_to_api_query_structure(query_structure),
        studies=[_build_study_summary(s) for s in execution.studies],
        timing=SearchTiming(
            lookup_ms=lookup_ms,
            pipeline_ms=pipeline_ms,
            total_ms=pipeline_ms + lookup_ms,
        ),
        total_studies=len(execution.studies),
        total_variables=execution.total_variable_count,
        variables=[_build_variable_result(r) for r in execution.variable_rows],
    )

    # Persist conversation state for the next turn. Both histories are bounded
    # on write so stored state can't grow without limit (matters once the store
    # is DynamoDB, with per-item size caps). Stopgap — a coherent truncation
    # policy for both is tracked in #380.
    state.query = query_model
    state.pending = deps.pending
    state.agent_message_history = serialize_history(
        truncate_history(new_history, _MAX_AGENT_HISTORY)
    )
    state.messages.append(ConversationMessage(content=request.query, role="user"))
    state.messages.append(ConversationMessage(content=reply, role="assistant"))
    state.messages = state.messages[-_MAX_SESSION_MESSAGES:]
    try:
        await store.save(request.session_id, state)
    except Exception as exc:  # noqa: BLE001 — the response is built; a persist failure must not 500
        _log_json(
            event="agent_store_error",
            op="save",
            session_id=request.session_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )

    _log_json(
        event="agent_response",
        session_id=request.session_id,
        query=request.query,
        intent=query_model.intent,
        total_studies=len(execution.studies),
        total_variables=execution.total_variable_count,
        pipeline_ms=pipeline_ms,
        lookup_ms=lookup_ms,
    )
    return response


@app.post("/search/agent/filter", response_model=SearchResponse)
async def search_agent_filter(
    request: SearchAgentFilterRequest, fastapi_request: Request
) -> SearchResponse | JSONResponse:
    """Structured filter removal for agent mode (#382).

    Deterministic sibling of ``/search/agent`` — no LLM turn. Drops one facet
    value from the session's persisted query state, re-runs the lookup, and
    saves the session. The next conversational turn sees the updated filters
    because the state preamble is rebuilt from ``state.query`` each turn.
    """
    client_ip = _get_client_ip(fastapi_request)
    if not await _rate_limiter.is_allowed(client_ip):
        return _rate_limit_response(client_ip, f"remove {request.facet.value}={request.value}")

    _log_json(
        event="agent_filter_request",
        session_id=request.session_id,
        facet=request.facet.value,
        value=request.value,
    )
    t_start = time.monotonic()

    store = get_session_store()
    try:
        state = await store.get(request.session_id) or SessionState()
    except Exception as exc:  # noqa: BLE001 — a store read failure is retryable, not a 500
        _log_json(
            event="agent_store_error",
            op="get",
            session_id=request.session_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        return _timeout_response(elapsed_ms, "Something went wrong — please try again.")

    query_model = _remove_filter_value(state.query or QueryModel(), request.facet, request.value)

    index = get_index()
    execution = execute_query_model(query_model, index)
    t_lookup = time.monotonic()
    lookup_ms = int((t_lookup - t_start) * 1000)

    query_structure = build_query_structure(query_model, index)
    message = _build_response_message(
        query_model,
        query_structure,
        execution.studies,
        execution.variable_rows,
        execution.total_variable_count,
        index,
    )
    response = SearchResponse(
        intent=query_model.intent,
        message=message,
        query=query_model,
        query_structure=_to_api_query_structure(query_structure),
        studies=[_build_study_summary(s) for s in execution.studies],
        timing=SearchTiming(lookup_ms=lookup_ms, pipeline_ms=0, total_ms=lookup_ms),
        total_studies=len(execution.studies),
        total_variables=execution.total_variable_count,
        variables=[_build_variable_result(r) for r in execution.variable_rows],
    )

    # Persist the updated query so the next agent turn reasons over it.
    state.query = query_model
    try:
        await store.save(request.session_id, state)
    except Exception as exc:  # noqa: BLE001 — the response is built; a persist failure must not 500
        _log_json(
            event="agent_store_error",
            op="save",
            session_id=request.session_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )

    _log_json(
        event="agent_filter_response",
        session_id=request.session_id,
        facet=request.facet.value,
        value=request.value,
        intent=query_model.intent,
        total_studies=len(execution.studies),
        total_variables=execution.total_variable_count,
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
