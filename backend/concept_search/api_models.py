"""Pydantic models for the HTTP API layer.

Separate from models.py to avoid coupling HTTP transport concerns
(camelCase serialization, field subsetting) to pipeline domain models.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .models import Intent, QueryModel


class SearchRequest(BaseModel):
    """Incoming search query.

    Three modes based on which fields are present:

    1. **Fresh** — ``query`` is set, no ``previous_query``.  Full pipeline.
    2. **Refine** — ``query`` is set *and* ``previous_query`` is present.
       Extract only new mentions, merge onto previous state.
    3. **Lookup-only** — ``query`` is empty/absent, ``previous_query`` is
       present.  Skip LLM pipeline; re-run deterministic lookup with the
       (possibly mutated) previous query model.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    previous_query: QueryModel | None = None
    query: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_query_or_previous(self) -> SearchRequest:
        """Ensure at least one of query or previous_query is provided."""
        if not (self.query and self.query.strip()) and self.previous_query is None:
            raise ValueError(
                "Either 'query' must be non-empty or 'previousQuery' must be provided."
            )
        return self


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
    """Top-level response for POST /search."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    intent: Intent = "study"
    message: str | None
    query: QueryModel
    studies: list[StudySummary] = Field(default_factory=list)
    timing: SearchTiming
    total_studies: int = 0
    total_variables: int = 0
    variables: list[VariableResult] = Field(default_factory=list)
