"""Endpoint tests for the agentic ``/search/agent`` route (no LLM calls).

The orchestrator (``run_conversation``) and the index are mocked, so these
tests exercise only the HTTP wiring: request validation, rate limiting, the
session-state load/persist round trip, response shaping, and graceful
timeout/error handling. The agent's own behaviour is covered by the eval
harnesses (``eval_agent_conversation`` / ``eval_agent_decision``).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from concept_search import api as api_module
from concept_search.api import app
from concept_search.models import Facet, QueryModel, ResolvedMention
from concept_search.session_store import InMemorySessionStore, SessionState


def _study(title: str = "Study A", db_gap_id: str = "phs000001") -> dict:
    """Build a minimal study dict shaped like a store row."""
    return {
        "consentCodes": [],
        "dataTypes": [],
        "dbGapId": db_gap_id,
        "focus": "Diabetes Mellitus",
        "participantCount": 100,
        "platforms": ["AnVIL"],
        "studyDesigns": [],
        "title": title,
    }


def _query(text: str = "diabetes") -> QueryModel:
    """A committed study-intent query with one resolved focus mention."""
    return QueryModel(
        intent="study",
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text=text,
                values=["Diabetes Mellitus"],
            )
        ],
    )


def _recording_run(seen: list[list[str]]):
    """Build a run_conversation stub that records each turn's incoming query_state.

    Appends the ``original_text`` of every mention the orchestrator was handed
    (i.e. the persisted state loaded for this turn) to ``seen``, so tests can
    assert what prior state carried over.
    """

    def fake_run(message, deps, message_history=None, model=None):
        seen.append([m.original_text for m in deps.query_state.mentions])
        return (f"reply: {message}", _query(), [])

    return fake_run


def _multi_value_query() -> QueryModel:
    """A query with a two-value focus mention plus a platform mention."""
    return QueryModel(
        intent="study",
        mentions=[
            ResolvedMention(
                facet=Facet.FOCUS,
                original_text="diabetes",
                values=["Diabetes Mellitus", "Diabetes Mellitus, Type 2"],
            ),
            ResolvedMention(
                facet=Facet.PLATFORM,
                original_text="anvil",
                values=["AnVIL"],
            ),
        ],
    )


def _seed_session(store: InMemorySessionStore, session_id: str, query: QueryModel) -> None:
    """Persist a session with the given committed query state."""
    asyncio.run(store.save(session_id, SessionState(query=query)))


@pytest.fixture
def agent_store():
    """A fresh in-memory session store patched into the API module."""
    store = InMemorySessionStore()
    with patch("concept_search.api.get_session_store", return_value=store):
        yield store


@pytest.fixture
def agent_client(agent_store):
    """A TestClient backed by a fresh in-memory session store per test."""
    yield TestClient(app, raise_server_exceptions=False)


class TestSearchAgentEndpoint:
    """HTTP-level tests for POST /search/agent."""

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_happy_path_returns_search_response(self, mock_index, mock_run, agent_client) -> None:
        """A successful turn returns 200 with the agent reply and matched studies."""
        mock_index.return_value.query_studies.return_value = [_study()]
        mock_index.return_value.stats = {}
        mock_run.return_value = ("Here are diabetes studies.", _query(), [])

        resp = agent_client.post(
            "/search/agent",
            json={"query": "diabetes studies", "sessionId": "s1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Here are diabetes studies."
        assert data["totalStudies"] == 1
        assert data["studies"][0]["title"] == "Study A"
        assert data["intent"] == "study"

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_store_get_failure_returns_friendly_error(self, mock_index, mock_run) -> None:
        """A session-store read failure surfaces a retryable message, not a 500."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}
        store = InMemorySessionStore()
        store.get = AsyncMock(side_effect=RuntimeError("dynamodb unavailable"))

        with patch("concept_search.api.get_session_store", return_value=store):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/search/agent", json={"query": "x", "sessionId": "s1"})

        assert resp.status_code == 200  # graceful, not an unhandled 500
        assert "went wrong" in resp.json()["message"].lower()
        mock_run.assert_not_called()  # bailed before running the orchestrator

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_store_save_failure_still_returns_response(self, mock_index, mock_run) -> None:
        """A persist failure after the response is built does not fail the request."""
        mock_index.return_value.query_studies.return_value = [_study()]
        mock_index.return_value.stats = {}
        mock_run.return_value = ("Here are diabetes studies.", _query(), [])
        store = InMemorySessionStore()
        store.save = AsyncMock(side_effect=RuntimeError("dynamodb unavailable"))

        with patch("concept_search.api.get_session_store", return_value=store):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/search/agent", json={"query": "diabetes", "sessionId": "s1"})

        assert resp.status_code == 200
        assert resp.json()["message"] == "Here are diabetes studies."

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_session_continuity_loads_prior_state(
        self, mock_index, mock_run, agent_client
    ) -> None:
        """Turn 2 reuses turn 1's persisted query state for the same session id."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        seen: list[list[str]] = []
        mock_run.side_effect = _recording_run(seen)

        r1 = agent_client.post("/search/agent", json={"query": "diabetes", "sessionId": "s1"})
        r2 = agent_client.post("/search/agent", json={"query": "only on BDC", "sessionId": "s1"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Turn 1 started from empty state; turn 2 saw turn 1's committed query.
        assert seen[0] == []
        assert seen[1] == ["diabetes"]

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_separate_sessions_are_isolated(self, mock_index, mock_run, agent_client) -> None:
        """A different session id does not inherit another session's state."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        seen: list[list[str]] = []
        mock_run.side_effect = _recording_run(seen)

        agent_client.post("/search/agent", json={"query": "diabetes", "sessionId": "s1"})
        agent_client.post("/search/agent", json={"query": "asthma", "sessionId": "s2"})

        assert seen[0] == []  # s1 first turn
        assert seen[1] == []  # s2 first turn — not polluted by s1

    @patch("concept_search.api.get_index")
    def test_rate_limit_returns_429(self, mock_index) -> None:
        """A rate-limited client gets a 429 before the orchestrator runs."""
        with (
            patch.object(
                api_module._rate_limiter, "is_allowed", new=AsyncMock(return_value=False)
            ),
            patch("concept_search.api.run_conversation") as mock_run,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/search/agent", json={"query": "x", "sessionId": "s1"})

        assert resp.status_code == 429
        mock_run.assert_not_called()

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_timeout_returns_graceful_response(self, mock_index, mock_run, agent_client) -> None:
        """An orchestrator timeout yields an empty 200 with a friendly message."""
        mock_index.return_value.stats = {}
        mock_run.side_effect = TimeoutError

        resp = agent_client.post("/search/agent", json={"query": "x", "sessionId": "s1"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["totalStudies"] == 0
        assert data["studies"] == []
        assert "timed out" in data["message"].lower()

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_orchestrator_error_returns_graceful_response(
        self, mock_index, mock_run, agent_client
    ) -> None:
        """An unexpected orchestrator error yields an empty 200, not a 500."""
        mock_index.return_value.stats = {}
        mock_run.side_effect = RuntimeError("boom")

        resp = agent_client.post("/search/agent", json={"query": "x", "sessionId": "s1"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["totalStudies"] == 0
        assert "went wrong" in data["message"].lower()

    @patch("concept_search.api.get_index")
    def test_missing_session_id_is_rejected(self, mock_index) -> None:
        """A request without a session id fails validation (422)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search/agent", json={"query": "diabetes"})
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_empty_session_id_is_rejected(self, mock_index) -> None:
        """An empty session id fails validation (min_length=1)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search/agent", json={"query": "diabetes", "sessionId": ""})
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_missing_query_is_rejected(self, mock_index) -> None:
        """A request without a query fails validation — the agent needs a message."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search/agent", json={"sessionId": "s1"})
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_blank_query_is_rejected(self, mock_index) -> None:
        """A whitespace-only query fails validation."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search/agent", json={"query": "   ", "sessionId": "s1"})
        assert resp.status_code == 422


class TestSearchAgentFilterEndpoint:
    """HTTP-level tests for POST /search/agent/filter (structured chip removal)."""

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_removes_single_value_keeps_mention(
        self, mock_index, mock_run, agent_store, agent_client
    ) -> None:
        """Removing one of two OR-ed values keeps the mention with the rest — no LLM call."""
        mock_index.return_value.query_studies.return_value = [_study()]
        mock_index.return_value.stats = {}
        _seed_session(agent_store, "s1", _multi_value_query())

        resp = agent_client.post(
            "/search/agent/filter",
            json={"facet": "focus", "sessionId": "s1", "value": "Diabetes Mellitus"},
        )

        assert resp.status_code == 200
        data = resp.json()
        focus = [m for m in data["query"]["mentions"] if m["facet"] == "focus"]
        assert len(focus) == 1
        assert focus[0]["values"] == ["Diabetes Mellitus, Type 2"]
        mock_run.assert_not_called()

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_removing_last_value_drops_mention(
        self, mock_index, mock_run, agent_store, agent_client
    ) -> None:
        """A mention emptied by the removal is dropped entirely."""
        mock_index.return_value.query_studies.return_value = [_study()]
        mock_index.return_value.stats = {}
        _seed_session(agent_store, "s1", _multi_value_query())

        resp = agent_client.post(
            "/search/agent/filter",
            json={"facet": "platform", "sessionId": "s1", "value": "AnVIL"},
        )

        assert resp.status_code == 200
        facets = [m["facet"] for m in resp.json()["query"]["mentions"]]
        assert facets == ["focus"]

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_removal_is_persisted_for_next_agent_turn(
        self, mock_index, mock_run, agent_store, agent_client
    ) -> None:
        """The next /search/agent turn is handed the query state minus the removed filter."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}
        _seed_session(agent_store, "s1", _multi_value_query())

        seen: list[list[str]] = []
        mock_run.side_effect = _recording_run(seen)

        r1 = agent_client.post(
            "/search/agent/filter",
            json={"facet": "focus", "sessionId": "s1", "value": "Diabetes Mellitus, Type 2"},
        )
        r2 = agent_client.post("/search/agent", json={"query": "and BMI", "sessionId": "s1"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        # The agent turn saw the persisted state with the platform mention intact
        # and the focus mention still present (one value remained).
        assert seen == [["diabetes", "anvil"]]
        state = asyncio.run(agent_store.get("s1"))
        assert state is not None

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_unknown_session_returns_empty_query(
        self, mock_index, mock_run, agent_store, agent_client
    ) -> None:
        """A filter removal on an unknown session degrades to an empty query, not an error."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        resp = agent_client.post(
            "/search/agent/filter",
            json={"facet": "focus", "sessionId": "missing", "value": "Diabetes Mellitus"},
        )

        assert resp.status_code == 200
        assert resp.json()["query"]["mentions"] == []

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_store_get_failure_returns_friendly_error(self, mock_index, mock_run) -> None:
        """A session-store read failure surfaces a retryable message, not a 500."""
        mock_index.return_value.stats = {}
        store = InMemorySessionStore()
        store.get = AsyncMock(side_effect=RuntimeError("dynamodb unavailable"))

        with patch("concept_search.api.get_session_store", return_value=store):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/search/agent/filter",
                json={"facet": "focus", "sessionId": "s1", "value": "x"},
            )

        assert resp.status_code == 200
        assert "went wrong" in resp.json()["message"].lower()

    @patch("concept_search.api.run_conversation")
    @patch("concept_search.api.get_index")
    def test_store_save_failure_still_returns_response(self, mock_index, mock_run) -> None:
        """A persist failure after the response is built does not fail the request."""
        mock_index.return_value.query_studies.return_value = [_study()]
        mock_index.return_value.stats = {}
        store = InMemorySessionStore()
        _seed_session(store, "s1", _multi_value_query())
        store.save = AsyncMock(side_effect=RuntimeError("dynamodb unavailable"))

        with patch("concept_search.api.get_session_store", return_value=store):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/search/agent/filter",
                json={"facet": "platform", "sessionId": "s1", "value": "AnVIL"},
            )

        assert resp.status_code == 200
        facets = [m["facet"] for m in resp.json()["query"]["mentions"]]
        assert facets == ["focus"]

    @patch("concept_search.api.get_index")
    def test_invalid_facet_is_rejected(self, mock_index) -> None:
        """An unknown facet fails validation (422)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/search/agent/filter",
            json={"facet": "nonsense", "sessionId": "s1", "value": "x"},
        )
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_missing_session_id_is_rejected(self, mock_index) -> None:
        """A request without a session id fails validation (422)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search/agent/filter", json={"facet": "focus", "value": "x"})
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_rate_limit_returns_429(self, mock_index) -> None:
        """A rate-limited client gets a 429 before any store access."""
        with (
            patch.object(
                api_module._rate_limiter, "is_allowed", new=AsyncMock(return_value=False)
            ),
            patch("concept_search.api.get_session_store") as mock_store,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/search/agent/filter",
                json={"facet": "focus", "sessionId": "s1", "value": "x"},
            )

        assert resp.status_code == 429
        mock_store.assert_not_called()
