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

from pydantic import BaseModel, ConfigDict, Field, model_validator
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


class DisambiguationOption(BaseModel):
    """One possible interpretation of an ambiguous mention."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    concept_id: str = Field(description="Canonical concept ID")
    label: str = Field(description="Human-readable label for this interpretation")


class MatchedVariable(BaseModel):
    """A specific variable that matched the user's query at a leaf concept."""

    description: str = Field(description="Variable description from the dataset")
    variable_name: str = Field(description="Variable name (e.g. 'A06SWT0100')")


class ResolveResult(BaseModel):
    """Output of the resolve agent for a single mention."""

    disambiguation: list[DisambiguationOption] = Field(
        default_factory=list,
        description="When the mention is ambiguous across distinct semantic "
        "domains, list 2-3 candidate interpretations here. Leave empty "
        "when resolution is confident.",
    )
    matched_variables: list[MatchedVariable] = Field(
        default_factory=list,
        description="Specific variables at a leaf concept whose descriptions "
        "match the user's query. Populated when the agent drills down to "
        "variable level. Empty when a concept-level match is sufficient.",
    )
    message: str | None = Field(
        default=None,
        description="Clarification message when the mention is ambiguous or "
        "cannot be resolved. None when resolution succeeds.",
    )
    values: list[str] = Field(
        description="Canonical value(s) from the index, combined with OR. "
        "Empty if the concept could not be resolved."
    )

    @model_validator(mode="after")
    def enforce_disambiguation_invariants(self) -> "ResolveResult":
        """Enforce mutual exclusivity and require a message for disambiguation."""
        if self.disambiguation:
            self.values = []
            # Always use deterministic formatting — don't trust LLM message
            lines = [f"- {d.label}" for d in self.disambiguation]
            self.message = (
                "Which did you mean?\n" + "\n".join(lines)
            )
        return self


# --- Structure agent / final query models ---


class ResolvedMention(BaseModel):
    """A fully resolved mention with boolean logic applied."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    disambiguation: list[DisambiguationOption] = Field(
        default_factory=list,
        description="Candidate interpretations when the mention is ambiguous "
        "across distinct semantic domains. Empty when resolved.",
    )
    exclude: bool = Field(
        default=False,
        description="True to exclude matching studies (NOT). "
        "False (default) to require them (AND).",
    )
    facet: Facet
    matched_variables: list[MatchedVariable] = Field(
        default_factory=list,
        description="Specific variables selected by the resolve agent at a "
        "leaf concept. Kept for display context in the API response but "
        "not used as a SQL filter — variable queries use ISA closure only.",
    )
    original_text: str = Field(description="The raw text from the user query")
    values: list[str] = Field(
        description="Resolved canonical value(s), combined with OR. "
        "Empty list if the concept could not be resolved.",
    )


# --- Router agent models ---

RouteKind = Literal["add", "remove", "replace", "reset", "select"]


class RouteSelect(BaseModel):
    """User selected one or more of the offered disambiguation options."""

    kind: Literal["select"] = "select"
    selected_ids: list[str] = Field(
        description="concept_id values from the disambiguation options the user chose."
    )


class RouteAdd(BaseModel):
    """User is adding new criteria to the existing query."""

    kind: Literal["add"] = "add"


class RouteRemove(BaseModel):
    """User wants to drop one or more mentions entirely."""

    kind: Literal["remove"] = "remove"
    original_texts: list[str] = Field(
        description="original_text values of the mentions to remove."
    )


class RouteReplace(BaseModel):
    """User wants to replace an existing mention with a different term."""

    kind: Literal["replace"] = "replace"
    original_text: str = Field(
        description="original_text of the mention to replace."
    )
    new_text: str = Field(
        description="The replacement term to extract and resolve."
    )


class RouteReset(BaseModel):
    """User is starting a completely new query."""

    kind: Literal["reset"] = "reset"
    new_query: str = Field(
        description="The new query to run fresh."
    )


RouterResult = RouteSelect | RouteAdd | RouteRemove | RouteReplace | RouteReset


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
