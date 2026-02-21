"""Pydantic models for concept search queries and results.

Three-agent pipeline models
---------------------------
1. **Extract agent** → ``ExtractResult`` containing ``RawMention`` items
2. **Resolve agent** → ``ResolveResult`` (values for a single mention)
3. **Structure agent** → ``QueryModel`` containing ``ResolvedMention`` items

Boolean semantics (QueryModel)
------------------------------
**Within a mention** — ``values`` are always combined with **OR**.

**Between mentions** — always **AND**, unless ``exclude=True`` (NOT).
Studies must satisfy every non-excluded mention.  Excluded mentions
subtract from the result set.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# Valid query intent values.
Intent = Literal["auto", "study", "variable"]


class Facet(str, Enum):
    """Searchable facets in the NCPI catalog."""

    COMPUTED_ANCESTRY = "computedAncestry"
    CONSENT_CODE = "consentCode"
    DATA_TYPE = "dataType"
    FOCUS = "focus"
    MEASUREMENT = "measurement"
    PLATFORM = "platform"
    RACE_ETHNICITY = "raceEthnicity"
    SEX = "sex"
    STUDY_DESIGN = "studyDesign"


# Small facets whose full value lists fit in the extract agent's prompt.
# The extract agent resolves these directly — no resolve agent call needed.
SMALL_FACETS = {
    Facet.COMPUTED_ANCESTRY,
    Facet.DATA_TYPE,
    Facet.PLATFORM,
    Facet.RACE_ETHNICITY,
    Facet.SEX,
    Facet.STUDY_DESIGN,
}


class ConceptMatch(BaseModel):
    """A concept/value found in the index."""

    facet: Facet
    study_count: int
    value: str


# --- Extract agent models ---


class RawMention(BaseModel):
    """A mention extracted from the user's query by the extract agent."""

    facet: Facet
    text: str = Field(description="The raw phrase from the user query")
    values: list[str] = Field(
        default_factory=list,
        description="Pre-resolved values for small facets (platform, dataType, "
        "studyDesign, sex, raceEthnicity, computedAncestry). "
        "Empty for facets that need the resolve agent.",
    )


class ExtractResult(BaseModel):
    """Output of the extract agent."""

    intent: Intent = Field(
        default="study",
        description="Query intent: 'study' to search datasets, 'variable' to "
        "search measured variables, 'auto' when ambiguous (ask user).",
    )
    mentions: list[RawMention] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Clarification message when the query is too vague or "
        "ambiguous to extract mentions from. None when extraction succeeds.",
    )


# --- Resolve agent models ---


class ResolveResult(BaseModel):
    """Output of the resolve agent for a single mention."""

    message: str | None = Field(
        default=None,
        description="Clarification message when the mention is ambiguous or "
        "cannot be resolved. None when resolution succeeds.",
    )
    values: list[str] = Field(
        description="Canonical value(s) from the index, combined with OR. "
        "Empty if the concept could not be resolved."
    )


# --- Structure agent / final query models ---


class ResolvedMention(BaseModel):
    """A fully resolved mention with boolean logic applied."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    exclude: bool = Field(
        default=False,
        description="True to exclude matching studies (NOT). "
        "False (default) to require them (AND).",
    )
    facet: Facet
    original_text: str = Field(description="The raw text from the user query")
    values: list[str] = Field(
        description="Resolved canonical value(s), combined with OR. "
        "Empty list if the concept could not be resolved.",
    )


class QueryModel(BaseModel):
    """Structured query output from the structure agent.

    All non-excluded mentions are AND-ed together.  Values within each
    mention are OR-ed.  Excluded mentions remove matching studies.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    intent: Intent = Field(
        default="study",
        description="Query intent carried through from extract agent.",
    )
    mentions: list[ResolvedMention] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Clarification message from the agents when the query "
        "is vague, ambiguous, or partially unresolved. None on success.",
    )
