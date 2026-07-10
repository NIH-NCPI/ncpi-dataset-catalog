"""Pin SINGLE_VALUED_FACETS to the actual catalog.

``update_query`` refuses to AND terms on a single-valued facet when no single
study can match all of them, telling the user so. That refusal is only correct
while the catalog agrees. If a study ever gains a second focus, the refusal would
start rejecting a query that has become answerable — so these tests fail loudly
rather than let that happen silently.

The counterpart matters too: ``platform`` is deliberately NOT single-valued
(6 studies span two platforms), and must never be added to the set.
"""

from __future__ import annotations

import json

import pytest

from concept_search.index import _resolve_paths
from concept_search.models import SINGLE_VALUED_FACETS, Facet

# Study-record field backing each facet whose cardinality we constrain.
_FIELD_BY_FACET = {
    Facet.FOCUS: "focus",
    Facet.PLATFORM: "platforms",
    Facet.STUDY_DESIGN: "studyDesigns",
}


def _catalog() -> list[dict]:
    """Load the study catalog the runtime would load, skipping if not built.

    Resolves through ``index._resolve_paths()`` rather than hardcoding a path, so
    that NCPI_PLATFORM_STUDIES_PATH / NCPI_REPO_ROOT point this test at the same
    file the agent will query. A hardcoded path silently validates a catalog the
    runtime never reads.

    Returns:
        Every study record in the catalog.
    """
    _llm_dir, path = _resolve_paths()
    if not path.exists():
        pytest.skip(f"catalog not built: {path}")
    with open(path) as f:
        return list(json.load(f).values())


def _cardinality(study: dict, field: str) -> int:
    """Count how many values of a facet field one study holds.

    Args:
        study: A study record.
        field: The study-record field backing the facet.

    Returns:
        Number of values, treating a scalar as one and a missing value as zero.
    """
    value = study.get(field)
    if isinstance(value, list):
        return len(value)
    return 1 if value else 0


@pytest.mark.parametrize("facet", sorted(SINGLE_VALUED_FACETS))
def test_single_valued_facet_holds_at_most_one_value(facet: Facet) -> None:
    """No study carries two values of a facet we treat as single-valued."""
    field = _FIELD_BY_FACET.get(facet)
    assert field is not None, (
        f"{facet.value} was added to SINGLE_VALUED_FACETS but not to _FIELD_BY_FACET, "
        f"so its cardinality is unverified. Add the study-record field backing it — "
        f"update_query refuses queries on this facet and must not do so unchecked."
    )
    offenders = [(s["dbGapId"], s[field]) for s in _catalog() if _cardinality(s, field) > 1]
    assert not offenders, (
        f"{facet.value} is in SINGLE_VALUED_FACETS but {len(offenders)} studies hold "
        f"more than one value (e.g. {offenders[:3]}). Either the catalog changed or "
        f"the facet no longer belongs in the set — an AND over it is now answerable."
    )


def test_platform_is_not_single_valued() -> None:
    """platform must stay out of the set: studies do span two platforms."""
    assert Facet.PLATFORM not in SINGLE_VALUED_FACETS
    multi = [s for s in _catalog() if _cardinality(s, "platforms") > 1]
    assert multi, (
        "No study spans two platforms any more. If that is a permanent property of "
        "the catalog, platform could join SINGLE_VALUED_FACETS — but verify first."
    )
