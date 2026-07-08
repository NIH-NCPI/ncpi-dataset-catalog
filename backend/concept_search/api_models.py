"""Pydantic models for the HTTP API layer.

Separate from models.py to avoid coupling HTTP transport concerns
(camelCase serialization, field subsetting) to pipeline domain models.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .models import Facet, Intent, QueryModel


class QueryClause(BaseModel):
    """A single clause in the structured query breakdown."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    exclude: bool = False
    facet: Facet
    labels: list[str]
    operator: str = "AND"


class QueryStructure(BaseModel):
    """Structured representation of the resolved query for frontend rendering."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    clauses: list[QueryClause]
    intent: Intent
    summary: str = ""


class SearchAgentRequest(BaseModel):
    """Incoming message for the agentic ``/search/agent`` endpoint.

    The backend owns conversation state keyed by ``session_id`` (via the
    SessionStore), so the client only sends a session id and the new message.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str = Field(max_length=1000)
    session_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_non_empty_query(self) -> SearchAgentRequest:
        """Reject a whitespace-only ``query``.

        ``query`` is required (a missing field is rejected by the schema); this
        additionally guards against a blank message. The agent path carries no
        ``previousQuery`` — conversation state lives server-side — so every turn
        must supply a real message to act on.
        """
        if not self.query.strip():
            raise ValueError("'query' must be a non-empty message.")
        return self


class SearchAgentFilterRequest(BaseModel):
    """Structured filter removal for the agentic ``/search/agent/filter`` endpoint.

    Sent when the user clicks the × on a filter chip in agent mode. This is a
    deterministic operation — no LLM turn: the backend drops the value from the
    session's persisted query state and re-runs the lookup. The next
    conversational turn sees the updated filters via the state preamble, which
    is rebuilt from the persisted query each turn.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    facet: Facet
    session_id: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=500)


class DemographicCategory(BaseModel):
    """A single category within a demographic distribution."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    count: int
    label: str
    percent: float


class DemographicDistribution(BaseModel):
    """Distribution of a single demographic dimension (sex, race, ancestry)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    categories: list[DemographicCategory]
    n: int


class StudyDemographics(BaseModel):
    """Demographic distributions for a study."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    computed_ancestry: DemographicDistribution | None = None
    race_ethnicity: DemographicDistribution | None = None
    sex: DemographicDistribution | None = None


class StudySummary(BaseModel):
    """Lean study projection — strips description, publications, etc."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    consent_codes: list[str]
    data_types: list[str]
    db_gap_id: str
    demographics: StudyDemographics | None = None
    focus: str | None
    participant_count: int | None
    platforms: list[str]
    study_designs: list[str]
    title: str


class SearchTiming(BaseModel):
    """Wall-clock timing breakdown for a search request."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    lookup_ms: int
    pipeline_ms: int
    total_ms: int


class VariableResult(BaseModel):
    """A single variable matching a concept query."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    concept: str
    concept_id: str
    cui: str | None
    dataset_id: str
    db_gap_url: str
    description: str
    phv_id: str
    study_id: str
    study_title: str
    study_url: str
    table_name: str
    variable_name: str


class SearchResponse(BaseModel):
    """Top-level response for the search endpoints (``/search/agent``)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    intent: Intent = "study"
    message: str | None
    query: QueryModel
    query_structure: QueryStructure | None = None
    studies: list[StudySummary] = Field(default_factory=list)
    timing: SearchTiming
    total_studies: int = 0
    total_variables: int = 0
    variables: list[VariableResult] = Field(default_factory=list)
