"""Pydantic models for the HTTP API layer.

Separate from models.py to avoid coupling HTTP transport concerns
(camelCase serialization, field subsetting) to pipeline domain models.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .models import QueryModel


class SearchRequest(BaseModel):
    """Incoming search query."""

    query: str = Field(..., min_length=1, max_length=1000)


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


class SearchResponse(BaseModel):
    """Top-level response for POST /search."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message: str | None
    query: QueryModel
    studies: list[StudySummary]
    timing: SearchTiming
    total_studies: int
