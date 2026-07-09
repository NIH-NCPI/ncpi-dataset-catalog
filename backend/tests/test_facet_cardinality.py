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
from pathlib import Path

import pytest

from concept_search.models import SINGLE_VALUED_FACETS, Facet

# Study-record field backing each facet whose cardinality we constrain.
_FIELD_BY_FACET = {
    Facet.FOCUS: "focus",
    Facet.PLATFORM: "platforms",
    Facet.STUDY_DESIGN: "studyDesigns",
}


def _catalog() -> list[dict]:
    """Load the study catalog, skipping the test when it is not built.

    Returns:
        Every study record in the catalog.
    """
    path = Path(__file__).resolve().parents[2] / "catalog" / "ncpi-platform-studies.json"
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
    field = _FIELD_BY_FACET[facet]
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
