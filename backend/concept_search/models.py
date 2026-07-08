"""Pydantic models for concept search queries and results.

The agent loop grounds each user term via the resolve agent (``ResolveResult``)
and commits selections into a ``QueryModel`` of ``ResolvedMention`` items.

Boolean semantics (QueryModel)
------------------------------
**Within a mention** — ``values`` are always combined with **OR**.

**Between mentions** — always **AND**, unless ``exclude=True`` (NOT).
Studies must satisfy every non-excluded mention.  Excluded mentions
subtract from the result set.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# Valid query intent values.
Intent = Literal["ambiguous", "study", "variable"]


class Facet(StrEnum):
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


class ConceptMatch(BaseModel):
    """A concept/value found in the index."""

    facet: Facet
    study_count: int
    value: str


# --- Mention models ---


class RawMention(BaseModel):
    """A raw user term to ground, with candidate facets (fed to the resolve agent)."""

    facets: list[Facet] = Field(
        description="Candidate facets ranked by confidence. Most mentions have "
        "one facet; ambiguous terms (e.g. 'glucose' could be focus or "
        "measurement) list multiple candidates.",
    )
    text: str = Field(description="The raw phrase from the user query")


# --- Resolve agent models ---


class DisambiguationOption(BaseModel):
    """One possible interpretation of an ambiguous mention."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    concept_id: str = Field(description="Canonical concept ID")
    facet: Facet | None = Field(
        default=None,
        description="Which facet this interpretation belongs to. "
        "Set automatically by the resolve agent.",
    )
    label: str = Field(description="Human-readable label for this interpretation")


class PendingChoice(BaseModel):
    """An open disambiguation the agent offered but the user hasn't resolved.

    Carried across conversation turns so an ordinal / "neither" reply has a
    referent. Distinct from a committed filter — the user still has to pick.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    facet: str = Field(description="Facet of the ambiguous term.")
    options: list[DisambiguationOption] = Field(
        default_factory=list, description="The candidate interpretations offered."
    )
    text: str = Field(description="The original user text that was ambiguous.")


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
    def enforce_disambiguation_invariants(self) -> ResolveResult:
        """Enforce mutual exclusivity and require a message for disambiguation."""
        if self.disambiguation:
            self.values = []
            # Always use deterministic formatting — don't trust LLM message
            lines = [f"- {d.label}" for d in self.disambiguation]
            self.message = "Which did you mean?\n" + "\n".join(lines)
        return self


# --- Query models ---


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


class QueryModel(BaseModel):
    """The structured query the conversation agent builds and maintains.

    All non-excluded mentions are AND-ed together.  Values within each
    mention are OR-ed.  Excluded mentions remove matching studies.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    intent: Intent = Field(
        default="study",
        description="Query intent (study | variable | ambiguous).",
    )
    mentions: list[ResolvedMention] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Clarification message from the agents when the query "
        "is vague, ambiguous, or partially unresolved. None on success.",
    )


# --- Conversation / session models ---


class ConversationMessage(BaseModel):
    """A single text turn in the conversation history.

    Only the user/assistant text is persisted — never the per-turn tool
    scratchpad. See ``session_store.SessionState``.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    content: str = Field(description="The message text.")
    role: Literal["user", "assistant"] = Field(description="Who produced the message.")
