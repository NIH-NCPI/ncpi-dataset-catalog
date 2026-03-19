"""Build human-readable response summaries and empty-result diagnostics.

Deterministic string formatting — no LLM calls.  Resolves concept IDs
to labels, renders boolean query structure, and diagnoses zero-result
queries with drop-one-at-a-time analysis.
"""

from __future__ import annotations

from .index import ConceptIndex
from .mention_constraints import split_mentions
from .models import Facet, QueryModel, ResolvedMention

# Display names for platform short codes.
_PLATFORM_DISPLAY: dict[str, str] = {
    "AnVIL": "AnVIL",
    "BDC": "BioData Catalyst",
    "CRDC": "Cancer Research Data Commons",
    "KFDRC": "Kids First Data Resource Center",
    "dbGaP": "dbGaP",
}

# Facet → qualifier prefix for the english query rendering.
_FACET_PREFIX: dict[Facet, str] = {
    Facet.PLATFORM: "on",
    Facet.DATA_TYPE: "with",
    Facet.FOCUS: "in",
    Facet.STUDY_DESIGN: "with",
    Facet.CONSENT_CODE: "with consent",
    Facet.COMPUTED_ANCESTRY: "with ancestry",
    Facet.RACE_ETHNICITY: "with race/ethnicity",
    Facet.SEX: "with sex",
}


class QueryClause:
    """A single clause in the structured query breakdown."""

    __slots__ = ("exclude", "facet", "labels", "operator")

    def __init__(
        self,
        facet: Facet,
        labels: list[str],
        *,
        exclude: bool = False,
        operator: str = "AND",
    ) -> None:
        self.exclude = exclude
        self.facet = facet
        self.labels = labels
        self.operator = operator


class QueryStructure:
    """Structured representation of the resolved query."""

    __slots__ = ("clauses", "intent", "summary")

    def __init__(
        self,
        clauses: list[QueryClause],
        intent: str,
        summary: str = "",
    ) -> None:
        self.clauses = clauses
        self.intent = intent
        self.summary = summary


def _resolve_label(
    concept_id: str,
    facet: Facet,
    descriptions: dict[str, dict],
) -> str:
    """Resolve a concept ID or facet value to a human-readable label.

    Args:
        concept_id: The raw value from a mention's ``values`` list.
        facet: Which facet this value belongs to.
        descriptions: Concept descriptions dict from the index.

    Returns:
        A human-readable label string.
    """
    if facet == Facet.PLATFORM:
        return _PLATFORM_DISPLAY.get(concept_id, concept_id)
    if facet == Facet.MEASUREMENT:
        fallback = concept_id.split(":")[-1] if ":" in concept_id else concept_id
        info = descriptions.get(concept_id) if isinstance(descriptions, dict) else None
        if isinstance(info, dict):
            return info.get("name", fallback)
        return fallback
    # Small facets (dataType, focus, studyDesign, etc.) — values are already readable
    return concept_id


def _mention_to_clause(
    mention: ResolvedMention,
    descriptions: dict[str, dict],
) -> QueryClause:
    """Convert a resolved mention into a QueryClause."""
    labels = [_resolve_label(v, mention.facet, descriptions) for v in mention.values]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for lbl in labels:
        if lbl not in seen:
            seen.add(lbl)
            unique.append(lbl)
    # Values within a mention are OR-ed (handled by display join); the operator
    # field describes how this clause combines with other clauses (AND/NOT).
    return QueryClause(
        facet=mention.facet,
        labels=unique,
        exclude=mention.exclude,
        operator="NOT" if mention.exclude else "AND",
    )


def build_query_structure(
    query_model: QueryModel,
    index: ConceptIndex,
) -> QueryStructure | None:
    """Build a structured query representation from resolved mentions.

    Args:
        query_model: The resolved query model.
        index: The concept index (for label lookup).

    Returns:
        A QueryStructure, or None if there are no mentions.
    """
    if not query_model.mentions:
        return None
    descriptions = index._ensure_concept_descriptions()
    clauses = [
        _mention_to_clause(m, descriptions)
        for m in query_model.mentions
        if m.values  # skip unresolved mentions
    ]
    if not clauses:
        return None
    return QueryStructure(
        clauses=clauses,
        intent=query_model.intent,
    )


def _oxford_join(items: list[str], conjunction: str = "and") -> str:
    """Join items with commas and an oxford comma.

    Args:
        items: Strings to join.
        conjunction: "and" or "or".

    Returns:
        Joined string.
    """
    if len(items) == 0:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def _render_natural_query(
    clauses: list[QueryClause],
    intent: str,
    *,
    count_prefix: str = "",
) -> str:
    """Render the query as a natural-English sentence.

    Builds a sentence like:
    - "Found 28 studies in Cardiovascular Diseases where BMI and
      smoking were measured"
    - "Found 5 studies on BioData Catalyst where blood pressure
      was measured, excluding diabetes"
    - "Found 847 variables across 12 studies where blood pressure
      was measured"

    Args:
        clauses: Query clauses.
        intent: Query intent ("study" or "variable").
        count_prefix: Leading phrase (e.g. "Found 28 studies").

    Returns:
        Natural-language sentence.
    """
    measurements: list[str] = []
    focuses: list[str] = []
    platforms: list[str] = []
    data_types: list[str] = []
    other_qualifiers: list[str] = []
    excludes: list[str] = []

    for clause in clauses:
        if not clause.labels:
            continue
        joined = _oxford_join(clause.labels, "or")
        if clause.exclude:
            excludes.append(joined)
        elif clause.facet == Facet.MEASUREMENT:
            measurements.append(joined)
        elif clause.facet == Facet.FOCUS:
            focuses.append(joined)
        elif clause.facet == Facet.PLATFORM:
            platforms.append(joined)
        elif clause.facet == Facet.DATA_TYPE:
            data_types.append(joined)
        else:
            prefix = _FACET_PREFIX.get(clause.facet, "with")
            other_qualifiers.append(f"{prefix} {joined}")

    # Assemble parts in natural order:
    # {prefix} [in {focus}] [on {platform}] [with {dataType}]
    #   [where {measurements} is/were measured] [, excluding {X}]
    parts: list[str] = []
    parts.append(count_prefix or "Results")

    if focuses:
        # Multiple focus clauses are AND-ed; labels within a clause are OR-ed
        parts.append(f"with focus {_oxford_join(focuses, 'and')}")
    if platforms:
        parts.append(f"on {_oxford_join(platforms, 'and')}")
    for q in other_qualifiers:
        parts.append(q)

    # Build "where" clause(s): data type + measurements
    where_parts: list[str] = []
    if data_types:
        dt_joined = _oxford_join(data_types)
        dt_verb = "is" if len(data_types) == 1 else "are"
        where_parts.append(f"data type {dt_verb} {dt_joined}")
    if measurements:
        measure_phrase = " and ".join(measurements)
        # Base verb on clause count, not label count — "systolic BP or
        # diastolic BP" is one conceptual measurement (one clause, OR-ed).
        verb = "was" if len(measurements) == 1 else "were"
        where_parts.append(f"{measure_phrase} {verb} measured")
    if where_parts:
        parts.append(f"where {' and '.join(where_parts)}")

    sentence = " ".join(parts)

    if excludes:
        sentence += f", excluding {_oxford_join(excludes)}"

    return sentence + "."


def build_message(
    query_structure: QueryStructure | None,
    n_studies: int,
    n_variables: int,
    query_model: QueryModel,
) -> str | None:
    """Build the full response message for a successful query.

    Args:
        query_structure: The structured query (may be None).
        n_studies: Number of matching studies.
        n_variables: Total variable count.
        query_model: The query model.

    Returns:
        A message string, or None if there is no query structure.
    """
    if query_structure is None or not query_structure.clauses:
        return None

    clauses = query_structure.clauses
    intent = query_model.intent

    # Build count prefix for the merged header
    study_word = "study" if n_studies == 1 else "studies"
    if intent == "variable" and n_variables > 0:
        variable_word = "variable" if n_variables == 1 else "variables"
        if n_studies > 0:
            count_prefix = f"Found {n_studies} {study_word} with {n_variables} {variable_word}"
        else:
            count_prefix = f"Found {n_variables} {variable_word}"
    else:
        count_prefix = f"Found {n_studies} {study_word}"

    sentence = _render_natural_query(clauses, intent, count_prefix=count_prefix)
    query_structure.summary = sentence
    return sentence


def diagnose_empty_results(
    query_model: QueryModel,
    index: ConceptIndex,
) -> str:
    """Diagnose why a query returned zero results and suggest recovery.

    Performs drop-one-at-a-time analysis: for each mention, re-query
    without it and report how many studies would match.

    Args:
        query_model: The query with resolved mentions.
        index: The concept index for re-querying.

    Returns:
        A diagnostic message with recovery suggestions.
    """
    mentions = [m for m in query_model.mentions if m.values]
    if not mentions:
        return "No results found. Try rephrasing your query."

    descriptions = index._ensure_concept_descriptions()

    # Render the "no results" header using natural phrasing
    clauses = [_mention_to_clause(m, descriptions) for m in mentions]
    no_results_prefix = (
        "No results found" if query_model.intent == "variable" else "No studies found"
    )
    header = _render_natural_query(clauses, query_model.intent, count_prefix=no_results_prefix)

    # Single mention — skip drop analysis
    if len(mentions) == 1:
        return (
            f"{header}\n"
            "This concept has no indexed studies. Try rephrasing or using a more common term."
        )

    # Drop-one-at-a-time analysis
    drop_results: list[tuple[str, int]] = []
    for i, mention in enumerate(mentions):
        remaining = [m for j, m in enumerate(mentions) if j != i]
        include, exclude = split_mentions(remaining, index)
        matched = index.query_studies(include, exclude or None)
        count = len(matched)
        # Build a label for this mention
        label = mention.original_text
        drop_results.append((label, count))

    # Classify the results
    has_results = [(label, count) for label, count in drop_results if count > 0]
    has_results.sort(key=lambda x: -x[1])  # most results first

    if not has_results:
        # Case C: nothing matches even individually
        return (
            f"{header}\n"
            "Each filter alone returns no results. "
            "Try rephrasing or using more common terms."
        )

    # Count how many drops yield results
    bottlenecks = [(label, count) for label, count in drop_results if count == 0]

    lines = [header]
    if len(bottlenecks) >= len(drop_results) - 1 and len(has_results) <= 1:
        # Case A: single mention is the bottleneck
        for label, count in has_results[:3]:
            study_word = "study" if count == 1 else "studies"
            lines.append(f'Dropping "{label}" would match {count} {study_word}.')
    else:
        # Case B: intersection too narrow
        lines.append("Each filter alone has results, but the combination is too narrow.")
        suggestions = [
            f'"{label}" (\u2192 {count} {"study" if count == 1 else "studies"})'
            for label, count in has_results[:3]
        ]
        lines.append(f"Try removing {_oxford_join(suggestions, 'or')}.")

    return "\n".join(lines)
