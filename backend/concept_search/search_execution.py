"""Deterministic execution of a resolved ``QueryModel`` against the catalog.

Shared by the live ``/search`` endpoint and the agentic ``/search/agent``
endpoint so the lookup behaviour is identical: both build a ``QueryModel`` (via
different means) and run it through the same DuckDB lookup here. This module
does **not** decide the user-facing message — callers own that (deterministic
summary for ``/search``; the agent's prose for ``/search/agent``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .index import ConceptIndex
from .mention_constraints import split_mentions
from .models import Facet, QueryModel


@dataclass
class ExecutionResult:
    """Raw lookup output for a ``QueryModel`` (rows, not API models)."""

    studies: list[dict] = field(default_factory=list)
    total_variable_count: int = 0
    variable_rows: list[dict] = field(default_factory=list)


def execute_query_model(query_model: QueryModel, index: ConceptIndex) -> ExecutionResult:
    """Run a resolved query against the catalog and return matching rows.

    Branches on ``query_model.intent``:

    - ``ambiguous`` — no lookup (caller returns a clarification message only).
    - ``variable`` — apply study-level constraints, then query variables for the
      measurement concepts via ISA closure.
    - ``study`` (default) — faceted study search.

    Args:
        query_model: The resolved query with mentions and intent.
        index: ConceptIndex providing the study/variable store.

    Returns:
        An ExecutionResult with the matched study/variable rows and the
        pre-limit variable count.
    """
    result = ExecutionResult()
    if not query_model.mentions:
        return result

    include, exclude = split_mentions(query_model.mentions, index)
    intent = query_model.intent

    if intent == "ambiguous":
        return result

    if intent == "variable":
        # Apply study-level constraints (platform, dataType, etc.) first.
        non_measurement = [c for c in include if c[0] != Facet.MEASUREMENT]
        study_ids: set[str] | None = None
        if non_measurement:
            matched = index.query_studies(non_measurement, exclude or None)
            study_ids = {s.get("dbGapId", "") for s in matched}
        elif exclude:
            matched = index.query_studies([], exclude)
            study_ids = {s.get("dbGapId", "") for s in matched}

        # Collect measurement concepts and query variables via ISA closure
        # (matched_variables are kept for display but not used as a SQL filter).
        all_concepts: list[str] = []
        for m in query_model.mentions:
            if m.facet != Facet.MEASUREMENT or m.exclude:
                continue
            all_concepts.extend(m.values)

        if all_concepts or study_ids:
            rows, result.total_variable_count = index.store.query_variables(
                concepts=all_concepts or None,
                study_ids=study_ids,
            )
            result.variable_rows.extend(rows)
        return result

    result.studies = index.query_studies(include, exclude or None)
    return result
