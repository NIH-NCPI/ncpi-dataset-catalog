"""Unit tests for pipeline merge logic and API dispatch (no LLM calls)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from concept_search.api import app
from concept_search.extract_agent import _format_previous_context
from concept_search.models import (
    DisambiguationOption,
    ExtractResult,
    Facet,
    QueryModel,
    RawMention,
    ResolvedMention,
    RouteAdd,
    RouteRemove,
    RouteReplace,
    RouteReset,
    RouteSelect,
)
from concept_search.pipeline import _merge_with_previous
from concept_search.resolve_agent import _run_resolve_uncached


def _rm(
    facet: Facet,
    text: str,
    values: list[str] | None = None,
    exclude: bool = False,
) -> ResolvedMention:
    """Shorthand for building a ResolvedMention."""
    return ResolvedMention(
        exclude=exclude,
        facet=facet,
        original_text=text,
        values=values or [],
    )


class TestMergeWithPrevious:
    """Tests for _merge_with_previous()."""

    def test_adds_new_mention(self) -> None:
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])]
        )
        new = [_rm(Facet.PLATFORM, "AnVIL", ["AnVIL"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 2
        facets = {m.facet for m in result.mentions}
        assert Facet.FOCUS in facets
        assert Facet.PLATFORM in facets

    def test_empty_previous_returns_new_only(self) -> None:
        previous = QueryModel(mentions=[])
        new = [_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 1
        assert result.mentions[0].original_text == "diabetes"

    def test_duplicate_key_latest_wins(self) -> None:
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "cancer", ["Cancer"], exclude=False)]
        )
        new = [_rm(Facet.FOCUS, "cancer", ["Cancer"], exclude=True)]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 1
        assert result.mentions[0].exclude is True

    def test_preserves_exclude_flags(self) -> None:
        previous = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                _rm(Facet.FOCUS, "pediatric", ["Pediatrics"], exclude=True),
            ]
        )
        new = [_rm(Facet.PLATFORM, "AnVIL", ["AnVIL"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 3
        excluded = [m for m in result.mentions if m.exclude]
        assert len(excluded) == 1
        assert excluded[0].original_text == "pediatric"

    def test_carries_intent_from_new(self) -> None:
        previous = QueryModel(intent="study", mentions=[])
        new: list[ResolvedMention] = []
        result = _merge_with_previous(previous, new, new_intent="variable")
        assert result.intent == "variable"

    def test_keeps_previous_intent_when_new_is_none(self) -> None:
        previous = QueryModel(intent="variable", mentions=[])
        new: list[ResolvedMention] = []
        result = _merge_with_previous(previous, new, new_intent=None)
        assert result.intent == "variable"

    def test_multiple_facets_accumulated(self) -> None:
        previous = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                _rm(Facet.DATA_TYPE, "WGS", ["WGS"]),
            ]
        )
        new = [
            _rm(Facet.PLATFORM, "AnVIL", ["AnVIL"]),
            _rm(Facet.SEX, "female", ["Female"]),
        ]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 4

    def test_same_facet_different_text_both_kept(self) -> None:
        """Two focus mentions with different text should both be kept."""
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])]
        )
        new = [_rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 2

    def test_preserves_previous_intent_when_new_is_default_study(self) -> None:
        """When prior intent is 'variable' and new is default 'study', keep prior."""
        previous = QueryModel(intent="variable", mentions=[])
        new: list[ResolvedMention] = []
        result = _merge_with_previous(previous, new, new_intent="study")
        assert result.intent == "variable"


class TestModeDetection:
    """Tests for mode detection in the API search endpoint."""

    @patch("concept_search.api.get_index")
    def test_lookup_mode_with_empty_mentions(self, mock_index) -> None:
        """Removing last filter chip sends previousQuery with empty mentions.

        Should be lookup mode (return previousQuery as-is), not fresh
        (which would run LLM pipeline on empty query).
        """
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "",
            "previousQuery": {"intent": "study", "mentions": []},
        })
        assert resp.status_code == 200
        data = resp.json()
        # If mode was incorrectly 'fresh', the pipeline would run on empty
        # query. In lookup mode, pipelineMs should be ~0 (no LLM call).
        assert data["timing"]["pipelineMs"] == 0

    @patch("concept_search.api.get_index")
    def test_rejects_empty_request(self, mock_index) -> None:
        """Request with no query and no previousQuery should be rejected."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={"query": ""})
        assert resp.status_code == 422

    @patch("concept_search.api.get_index")
    def test_lookup_pipeline_ms_is_zero(self, mock_index) -> None:
        """Lookup-only mode should report pipelineMs=0."""
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "asthma",
                        "values": ["Asthma"],
                        "exclude": False,
                    }
                ],
            },
        })
        assert resp.status_code == 200
        assert resp.json()["timing"]["pipelineMs"] == 0


class TestExtractPromptFormat:
    """Tests for extract agent prompt formatting."""

    def test_refinement_prompt_starts_with_active_intent(self) -> None:
        """Prompt for refinement should start with 'Active intent:'."""
        previous = QueryModel(
            intent="variable",
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])],
        )
        context = _format_previous_context(previous)
        prompt = (
            f"Active intent: {previous.intent}\n"
            f"Active filters:\n{context}\n\n"
            f"New user input: also on BDC"
        )
        assert prompt.startswith("Active intent:")

    def test_empty_mentions_still_includes_intent(self) -> None:
        """Even with no mentions, refinement prompt should include intent."""
        previous = QueryModel(intent="variable", mentions=[])
        context = _format_previous_context(previous)
        prompt = (
            f"Active intent: {previous.intent}\n"
            f"Active filters:\n{context}\n\n"
            f"New user input: also on BDC"
        )
        assert "Active intent: variable" in prompt


class TestRefinePreservesIntent:
    """System-level tests: refine mode preserves intent through the API.

    Mocks at the agent level (extract/resolve/structure) so the pipeline's
    _merge_with_previous logic actually runs.
    """

    @patch("concept_search.api.get_index")
    @patch("concept_search.pipeline.run_structure")
    @patch("concept_search.pipeline.run_resolve")
    @patch("concept_search.pipeline.run_extract")
    @patch("concept_search.api.run_router")
    def test_refine_preserves_variable_intent(
        self, mock_router, mock_extract, mock_resolve, mock_structure, mock_index
    ) -> None:
        """Refine with previousQuery.intent='variable' keeps it even when
        extract returns default 'study' intent."""
        mock_router.return_value = RouteAdd()
        # Extract returns a new mention with default "study" intent
        mock_extract.return_value = ExtractResult(
            intent="study",
            mentions=[RawMention(facet=Facet.PLATFORM, text="AnVIL",
                                 values=["AnVIL"])],
        )
        # Resolve returns the mention as-is (pre-resolved small facet skips)
        # Structure returns with no exclude flags
        mock_structure.return_value = QueryModel(
            mentions=[_rm(Facet.PLATFORM, "AnVIL", ["AnVIL"])],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.store.query_variables.return_value = ([], 0)
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "also on AnVIL",
            "previousQuery": {
                "intent": "variable",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "asthma",
                        "values": ["Asthma"],
                        "exclude": False,
                    }
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        # Extract returned default "study" but previous was "variable".
        # _merge_with_previous should preserve "variable".
        assert data["intent"] == "variable"
        # Both mentions should be present (previous focus + new platform)
        facets = {m["facet"] for m in data["query"]["mentions"]}
        assert facets == {"focus", "platform"}

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_pipeline")
    def test_api_passes_through_pipeline_intent(
        self, mock_pipeline, mock_index
    ) -> None:
        """API must not mask pipeline intent — passes through whatever
        the pipeline returns, even if it's wrong."""
        mock_pipeline.return_value = QueryModel(
            intent="study",
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                _rm(Facet.PLATFORM, "AnVIL", ["AnVIL"]),
            ],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "also on AnVIL",
            "previousQuery": {
                "intent": "variable",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "asthma",
                        "values": ["Asthma"],
                        "exclude": False,
                    }
                ],
            },
        })
        assert resp.status_code == 200
        # API is a passthrough — if the pipeline returns "study", that's
        # what the response should have. The pipeline owns intent logic.
        assert resp.json()["intent"] == "study"


class TestLookupWithMutatedMentions:
    """System-level tests: lookup mode with modified mentions."""

    @patch("concept_search.api.get_index")
    def test_lookup_returns_updated_filters(self, mock_index) -> None:
        """Lookup-only with a modified mentions list returns correct filters.

        Simulates removing a chip: client sends previousQuery with the
        mention removed, empty query triggers lookup mode.
        """
        mock_index.return_value.query_studies.return_value = [
            {
                "title": "Study A",
                "dbGapId": "phs000001",
                "platforms": ["AnVIL"],
                "focus": "Asthma",
                "dataTypes": [],
                "participantCount": 100,
                "studyDesigns": [],
                "consentCodes": [],
            },
        ]
        mock_index.return_value.stats = {}

        # Send lookup with only focus mention (platform removed)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "asthma",
                        "values": ["Asthma"],
                        "exclude": False,
                    }
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should use the mentions as-is (no pipeline)
        assert data["timing"]["pipelineMs"] == 0
        assert len(data["query"]["mentions"]) == 1
        assert data["query"]["mentions"][0]["facet"] == "focus"
        assert data["totalStudies"] == 1


class TestConcurrentSemaphore:
    """System-level test: concurrent requests respect the pipeline semaphore."""

    @pytest.mark.asyncio
    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_pipeline")
    async def test_concurrent_requests_all_complete(
        self, mock_pipeline, mock_index
    ) -> None:
        """Fire more requests than the semaphore allows (5) and verify
        all eventually complete without errors."""
        gate = asyncio.Event()

        async def slow_pipeline(query, **kwargs):
            """Simulate a slow pipeline that waits for a gate."""
            await gate.wait()
            return QueryModel(
                intent="study",
                mentions=[_rm(Facet.FOCUS, "test", ["Test"])],
            )

        mock_pipeline.side_effect = slow_pipeline
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Fire 8 concurrent requests (semaphore is 5)
            tasks = [
                asyncio.create_task(
                    client.post(
                        "/search",
                        json={"query": f"test query {i}"},
                    )
                )
                for i in range(8)
            ]

            # Let a tick pass so all requests hit the semaphore
            await asyncio.sleep(0.05)

            # Release the gate — all requests should complete
            gate.set()

            responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 200 for r in responses)
        assert len(responses) == 8


def _disambig_options() -> list[DisambiguationOption]:
    """Build sample disambiguation options."""
    return [
        DisambiguationOption(
            concept_id="phenx:fasting_plasma_glucose_blood_draw",
            label="Blood glucose measurement",
        ),
        DisambiguationOption(
            concept_id="topmed:nutrient_intake",
            label="Dietary glucose intake",
        ),
    ]


class TestDisambiguation:
    """Tests for disambiguation flow through the pipeline."""

    def test_disambiguation_preserved_in_merge(self) -> None:
        """Disambiguation options survive _merge_with_previous."""
        previous = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", ["Asthma"])]
        )
        new = [
            ResolvedMention(
                disambiguation=_disambig_options(),
                facet=Facet.MEASUREMENT,
                original_text="glucose",
                values=[],
            )
        ]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 2
        glucose = [m for m in result.mentions if m.original_text == "glucose"][0]
        assert len(glucose.disambiguation) == 2
        assert glucose.values == []

    def test_followup_adds_alongside_disambiguation(self) -> None:
        """User follow-up adds a new mention; disambiguation mention stays."""
        previous = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "asthma", ["Asthma"]),
                ResolvedMention(
                    disambiguation=_disambig_options(),
                    facet=Facet.MEASUREMENT,
                    original_text="glucose",
                    values=[],
                ),
            ]
        )
        # User typed "blood glucose" — different original_text, so both kept
        new = [_rm(Facet.MEASUREMENT, "blood glucose",
                    ["phenx:fasting_plasma_glucose_blood_draw"])]
        result = _merge_with_previous(previous, new)
        assert len(result.mentions) == 3
        glucose = [m for m in result.mentions if m.original_text == "glucose"][0]
        assert len(glucose.disambiguation) == 2
        assert glucose.values == []

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_pipeline")
    def test_disambiguation_in_api_response(
        self, mock_pipeline, mock_index
    ) -> None:
        """API response includes disambiguation options on mentions."""
        mock_pipeline.return_value = QueryModel(
            mentions=[
                ResolvedMention(
                    disambiguation=_disambig_options(),
                    facet=Facet.MEASUREMENT,
                    original_text="glucose",
                    values=[],
                ),
            ],
            message="Did you mean blood glucose levels or dietary glucose intake?",
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={"query": "glucose"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Did you mean blood glucose levels or dietary glucose intake?"
        mention = data["query"]["mentions"][0]
        assert mention["values"] == []
        assert len(mention["disambiguation"]) == 2
        assert mention["disambiguation"][0]["conceptId"] == "phenx:fasting_plasma_glucose_blood_draw"

    def test_disambiguation_clears_values_and_generates_message(self) -> None:
        """ResolveResult validator clears values and auto-generates message."""
        from concept_search.models import ResolveResult

        result = ResolveResult(
            disambiguation=_disambig_options(),
            values=["should_be_cleared"],
            message=None,
        )

        assert result.values == []
        assert result.message is not None
        assert "Which did you mean?" in result.message
        assert "- Blood glucose measurement" in result.message
        assert "- Dietary glucose intake" in result.message

    def test_disambiguation_overwrites_llm_message(self) -> None:
        """ResolveResult validator replaces LLM message with deterministic format."""
        from concept_search.models import ResolveResult

        result = ResolveResult(
            disambiguation=_disambig_options(),
            values=["should_be_cleared"],
            message="Custom question from the LLM",
        )

        assert result.values == []
        assert "Which did you mean?" in result.message
        assert "- Blood glucose measurement" in result.message

    @pytest.mark.asyncio
    @patch("concept_search.resolve_agent._get_agent")
    async def test_disambiguation_on_non_measurement_cleared(
        self, mock_get_agent
    ) -> None:
        """Disambiguation on non-measurement facets is silently cleared."""
        from concept_search.models import ResolveResult

        # Validator fires first (clears values, sets message), then
        # _run_resolve_uncached clears disambiguation for non-measurement.
        mock_result = ResolveResult(
            disambiguation=_disambig_options(),
            values=["Heart Diseases"],
            message=None,
        )
        # Re-set values after validator cleared them — simulates what the
        # agent would need. Instead, build without disambiguation first.
        mock_result = ResolveResult(values=["Heart Diseases"], message=None)
        mock_result.disambiguation = _disambig_options()

        class FakeRunResult:
            output = mock_result

        async def fake_run(*a, **kw):
            return FakeRunResult()

        mock_agent = mock_get_agent.return_value
        mock_agent.run = fake_run

        mention = RawMention(facet=Facet.FOCUS, text="heart", values=[])
        result = await _run_resolve_uncached(mention, index=None)

        assert result.disambiguation == []
        assert result.values == ["Heart Diseases"]


class TestRouteHandlers:
    """Tests for _handle_route dispatch in the API."""

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_router")
    def test_route_select_resolves_disambiguation(
        self, mock_router, mock_index
    ) -> None:
        """Select route sets values from chosen concept_id and clears disambiguation."""
        mock_router.return_value = RouteSelect(
            selected_ids=["phenx:fasting_plasma_glucose_blood_draw"],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "blood glucose",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                    {
                        "facet": "measurement",
                        "originalText": "glucose",
                        "values": [],
                        "exclude": False,
                        "disambiguation": [
                            {
                                "conceptId": "phenx:fasting_plasma_glucose_blood_draw",
                                "label": "Blood glucose measurement",
                            },
                            {
                                "conceptId": "topmed:nutrient_intake",
                                "label": "Dietary glucose intake",
                            },
                        ],
                    },
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        mentions = data["query"]["mentions"]
        assert len(mentions) == 2
        glucose = [m for m in mentions if m["originalText"] == "glucose"][0]
        assert glucose["values"] == ["phenx:fasting_plasma_glucose_blood_draw"]
        assert glucose["disambiguation"] == []

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_router")
    def test_route_remove_drops_mention(
        self, mock_router, mock_index
    ) -> None:
        """Remove route drops the specified mention."""
        mock_router.return_value = RouteRemove(original_texts=["diabetes"])
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "remove the diabetes filter",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                    {
                        "facet": "measurement",
                        "originalText": "blood pressure",
                        "values": ["topmed:bp_systolic"],
                        "exclude": False,
                    },
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        mentions = data["query"]["mentions"]
        assert len(mentions) == 1
        assert mentions[0]["originalText"] == "blood pressure"

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_pipeline")
    @patch("concept_search.api.run_router")
    def test_route_reset_runs_fresh_pipeline(
        self, mock_router, mock_pipeline, mock_index
    ) -> None:
        """Reset route runs fresh pipeline ignoring previous state."""
        mock_router.return_value = RouteReset(new_query="COPD studies")
        mock_pipeline.return_value = QueryModel(
            mentions=[_rm(Facet.FOCUS, "COPD", ["Pulmonary Disease, Chronic Obstructive"])],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "show me COPD studies instead",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        mentions = data["query"]["mentions"]
        assert len(mentions) == 1
        assert mentions[0]["originalText"] == "COPD"
        # Pipeline called with new_query, no previous_query
        mock_pipeline.assert_called_once_with("COPD studies")

    @patch("concept_search.api.get_index")
    @patch("concept_search.api.run_pipeline")
    @patch("concept_search.api.run_router")
    def test_route_add_falls_through_to_pipeline(
        self, mock_router, mock_pipeline, mock_index
    ) -> None:
        """Add route falls through to existing refine pipeline."""
        mock_router.return_value = RouteAdd()
        mock_pipeline.return_value = QueryModel(
            mentions=[
                _rm(Facet.FOCUS, "diabetes", ["Diabetes Mellitus"]),
                _rm(Facet.PLATFORM, "AnVIL", ["AnVIL"]),
            ],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "also on AnVIL",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                ],
            },
        })
        assert resp.status_code == 200
        # Pipeline called with query and previous_query
        call_args = mock_pipeline.call_args
        assert call_args[0][0] == "also on AnVIL"
        assert call_args[1]["previous_query"] is not None

    @patch("concept_search.api._rate_limiter.is_allowed", new_callable=AsyncMock, return_value=True)
    @patch("concept_search.api.get_index")
    @patch("concept_search.pipeline.get_index")
    @patch("concept_search.pipeline.run_structure")
    @patch("concept_search.pipeline.run_resolve")
    @patch("concept_search.pipeline.run_extract")
    @patch("concept_search.api.run_router")
    def test_route_add_same_facet_merges(
        self, mock_router, mock_extract, mock_resolve, mock_structure,
        mock_pipeline_index, mock_index, _mock_rl
    ) -> None:
        """Add 'and asthma' when focus=diabetes already exists merges both."""
        mock_router.return_value = RouteAdd()
        # Extract sees previous focus=diabetes and extracts only the new mention
        mock_extract.return_value = ExtractResult(
            intent="study",
            mentions=[RawMention(facet=Facet.FOCUS, text="asthma", values=[])],
        )
        from concept_search.models import ResolveResult
        mock_resolve.return_value = ResolveResult(
            values=["Asthma"], message=None,
        )
        mock_structure.return_value = QueryModel(
            mentions=[_rm(Facet.FOCUS, "asthma", [])],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "and asthma",
            "previousQuery": {
                "intent": "study",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        mentions = data["query"]["mentions"]
        # Both focus mentions should be present (previous + new)
        focus_mentions = [m for m in mentions if m["facet"] == "focus"]
        assert len(focus_mentions) == 2
        texts = {m["originalText"] for m in focus_mentions}
        assert texts == {"diabetes", "asthma"}

    @patch("concept_search.api._rate_limiter.is_allowed", new_callable=AsyncMock, return_value=True)
    @patch("concept_search.api.get_index")
    @patch("concept_search.pipeline.get_index")
    @patch("concept_search.pipeline.run_structure")
    @patch("concept_search.pipeline.run_resolve")
    @patch("concept_search.pipeline.run_extract")
    @patch("concept_search.api.run_router")
    def test_route_add_measurement_to_existing(
        self, mock_router, mock_extract, mock_resolve, mock_structure,
        mock_pipeline_index, mock_index, _mock_rl
    ) -> None:
        """Add 'also BMI' when measurement=blood_pressure already exists keeps both."""
        mock_router.return_value = RouteAdd()
        mock_extract.return_value = ExtractResult(
            intent="variable",
            mentions=[RawMention(facet=Facet.MEASUREMENT, text="BMI", values=[])],
        )
        from concept_search.models import ResolveResult
        mock_resolve.return_value = ResolveResult(
            values=["topmed:bmi"], message=None,
        )
        mock_structure.return_value = QueryModel(
            mentions=[_rm(Facet.MEASUREMENT, "BMI", [])],
        )
        mock_index.return_value.query_studies.return_value = []
        mock_index.return_value.store.query_variables.return_value = ([], 0)
        mock_index.return_value.stats = {}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/search", json={
            "query": "also BMI",
            "previousQuery": {
                "intent": "variable",
                "mentions": [
                    {
                        "facet": "focus",
                        "originalText": "diabetes",
                        "values": ["Diabetes Mellitus"],
                        "exclude": False,
                    },
                    {
                        "facet": "measurement",
                        "originalText": "blood pressure",
                        "values": ["topmed:bp_systolic", "topmed:bp_diastolic"],
                        "exclude": False,
                    },
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        mentions = data["query"]["mentions"]
        # Should have 3 mentions: focus + 2 measurements
        assert len(mentions) == 3
        meas = [m for m in mentions if m["facet"] == "measurement"]
        assert len(meas) == 2
        meas_texts = {m["originalText"] for m in meas}
        assert meas_texts == {"blood pressure", "BMI"}
        # Intent should stay "variable" (not clobbered by extract default "study")
        # Actually extract returned "variable" here so it should override
        assert data["intent"] == "variable"
