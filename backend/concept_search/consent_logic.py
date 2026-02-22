"""Deterministic consent code eligibility logic.

Pure functions — no LLM, no async. Parses GA4GH consent codes,
expands disease hierarchies, and computes the set of codes eligible
for a given research purpose.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "consent_codes.json"
_DISEASE_TSV_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "catalog-build"
    / "common"
    / "disease_abbrev_mapping.tsv"
)

# ---------------------------------------------------------------------------
# Load reference data once at module level
# ---------------------------------------------------------------------------

_data: dict = json.loads(_DATA_PATH.read_text())
_MODIFIERS: set[str] = set(_data.get("modifiers", {}))
_DISEASE_HIERARCHY: dict[str, list[str]] = _data.get("disease_hierarchy", {})

# Disease abbreviations from the authoritative TSV maintained in catalog-build
_DISEASE_ABBREVIATIONS: dict[str, str] = {}
if _DISEASE_TSV_PATH.exists():
    with _DISEASE_TSV_PATH.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            _DISEASE_ABBREVIATIONS[row["Disease abbrev"]] = row["Disease name"]
else:
    raise FileNotFoundError(
        f"Disease abbreviation mapping not found: {_DISEASE_TSV_PATH}"
    )

# Reverse map: lowercase disease name → abbreviation
_DISEASE_NAME_TO_ABBREV: dict[str, str] = {
    name.lower(): abbrev for abbrev, name in _DISEASE_ABBREVIATIONS.items()
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedConsentCode:
    """Structured representation of a parsed consent code."""

    base: str
    disease: str | None = None
    modifiers: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_consent_code(code: str) -> ParsedConsentCode:
    """Split a consent code string into base, disease, and modifiers.

    Uses the known modifier set to distinguish disease parts from modifier
    parts.  For example ``"DS-CVD-IRB-NPU"`` becomes
    ``ParsedConsentCode(base="DS", disease="CVD", modifiers={"IRB","NPU"})``.

    Args:
        code: A consent code string (e.g. ``"GRU-IRB"``).

    Returns:
        A :class:`ParsedConsentCode` with *base*, *disease*, and *modifiers*.
    """
    parts = code.split("-")
    base = parts[0]
    rest = parts[1:]

    # For DS codes, extract disease portion (everything before first modifier)
    disease: str | None = None
    mods: set[str] = set()

    if base == "DS" and rest:
        disease_parts: list[str] = []
        for part in rest:
            if part in _MODIFIERS:
                break
            disease_parts.append(part)
        disease = "-".join(disease_parts) if disease_parts else None
        # Remaining parts after disease are modifiers
        modifier_start = len(disease_parts)
        for part in rest[modifier_start:]:
            if part in _MODIFIERS:
                mods.add(part)
    else:
        # Non-DS codes: all remaining parts that are known modifiers
        for part in rest:
            if part in _MODIFIERS:
                mods.add(part)

    return ParsedConsentCode(base=base, disease=disease, modifiers=mods)


def expand_disease(disease: str) -> set[str]:
    """Expand a disease abbreviation to include all sub-diseases.

    Uses the ``disease_hierarchy`` from ``consent_codes.json``.  A parent
    disease like ``"DIAB"`` expands to ``{"DIAB", "T1D", "T2D", ...}``.
    Leaf diseases (not in the hierarchy) return just themselves.

    Args:
        disease: A disease abbreviation (e.g. ``"DIAB"``).

    Returns:
        Set containing the disease and all its children.
    """
    children = _DISEASE_HIERARCHY.get(disease, [])
    return {disease} | set(children)


def resolve_disease_name(name: str) -> str | None:
    """Map a disease name or abbreviation to a consent code abbreviation.

    Accepts either an abbreviation (``"DIAB"``) or a full/partial disease
    name (``"diabetes"``, ``"Breast Cancer"``).  Returns the abbreviation
    or ``None`` if no match is found.

    Args:
        name: A disease name or abbreviation.

    Returns:
        The disease abbreviation, or ``None``.
    """
    upper = name.upper()
    # Direct abbreviation match
    if upper in _DISEASE_ABBREVIATIONS:
        return upper
    # Full name match (case-insensitive)
    lower = name.lower()
    if lower in _DISEASE_NAME_TO_ABBREV:
        return _DISEASE_NAME_TO_ABBREV[lower]
    # Substring match: find abbreviation whose full name contains the query.
    # Prefer the shortest matching name (most specific match).
    best: tuple[str, int] | None = None
    for full_name, abbrev in _DISEASE_NAME_TO_ABBREV.items():
        if lower in full_name:
            if best is None or len(full_name) < best[1]:
                best = (abbrev, len(full_name))
    return best[0] if best else None


def compute_eligible_codes(
    all_codes: list[str],
    *,
    purpose: str = "general",
    disease: str | None = None,
    is_nonprofit: bool | None = None,
    explicit_code: str | None = None,
    disease_only: bool = False,
) -> list[str]:
    """Compute the set of consent codes eligible for a research use case.

    Two paths:

    - **Explicit code** — prefix-matches *explicit_code* against *all_codes*
      (e.g. ``"GRU"`` matches ``"GRU"``, ``"GRU-IRB"``, ``"GRU-NPU"``).
    - **Purpose** — determines eligibility by base code semantics:
      GRU is always eligible; HMB is eligible for ``"health"`` or
      ``"disease"`` purpose; DS-X is eligible when the user's disease
      falls within ``expand_disease(X)``.

    When *disease_only* is ``True``, only DS-* codes matching the disease
    are returned (GRU, HMB, etc. are excluded).  Use this when the user
    says "only", "specifically", or "disease-specific".

    In both paths, codes with an NPU modifier are excluded when
    *is_nonprofit* is ``False``.

    Args:
        all_codes: Every consent code value in the index.
        purpose: ``"general"``, ``"health"``, or ``"disease"``.
        disease: Disease abbreviation when *purpose* is ``"disease"``.
        is_nonprofit: ``True`` keeps all; ``False`` excludes NPU codes;
            ``None`` (default) keeps all.
        explicit_code: When set, uses prefix matching instead of purpose logic.
        disease_only: When ``True``, restricts results to DS-* codes only.

    Returns:
        Sorted list of eligible consent code strings.
    """
    eligible: list[str] = []

    # Expand the user's disease to include sub-diseases
    user_diseases: set[str] = set()
    if disease:
        user_diseases = expand_disease(disease)

    for code in all_codes:
        parsed = parse_consent_code(code)

        # NPU filter: if researcher is for-profit, exclude NPU-modified codes
        if is_nonprofit is False and "NPU" in parsed.modifiers:
            continue

        if explicit_code is not None:
            # Explicit code path: prefix match
            prefix = explicit_code.upper()
            if code.upper() == prefix or code.upper().startswith(prefix + "-"):
                eligible.append(code)
        else:
            # Purpose path
            if disease_only and parsed.base != "DS":
                continue
            if _is_eligible_by_purpose(parsed, purpose, user_diseases):
                eligible.append(code)

    eligible.sort()
    return eligible


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_eligible_by_purpose(
    parsed: ParsedConsentCode,
    purpose: str,
    user_diseases: set[str],
) -> bool:
    """Check if a parsed code is eligible for the given purpose."""
    base = parsed.base

    # GRU: always eligible for any purpose
    if base == "GRU":
        return True

    # HMB / HMP / HR: eligible for health or disease research
    if base in ("HMB", "HMP", "HR"):
        return purpose in ("health", "disease")

    # DS: eligible when the code's disease overlaps with user's disease set
    if base == "DS" and purpose == "disease" and parsed.disease:
        # Check if code's disease is in the user's expanded disease set,
        # OR if user's disease is a child of the code's disease
        code_diseases = expand_disease(parsed.disease)
        return bool(code_diseases & user_diseases)

    # Other base codes (NPU, CADM, IRU) are restriction/modifier codes,
    # not primary consent categories. They don't grant research use.
    return False
