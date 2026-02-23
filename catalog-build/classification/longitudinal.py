"""Heuristic longitudinal detection for dbGaP tables and variables.

Detects temporal patterns in table names and variable names to flag
longitudinal data collection (multi-visit, multi-exam studies).

Used by classify_with_memory.py as a pre-pass before LLM classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Table-name patterns (case-insensitive)
# ---------------------------------------------------------------------------

# Positive signals: table names containing temporal markers
_TABLE_POSITIVE_PATTERNS = [
    re.compile(r"exam\s*\d+", re.IGNORECASE),
    re.compile(r"visit\s*\d+", re.IGNORECASE),
    re.compile(r"wave\s*\d+", re.IGNORECASE),
    re.compile(r"follow.?up", re.IGNORECASE),
    re.compile(r"year\s*\d+", re.IGNORECASE),
    re.compile(r"baseline", re.IGNORECASE),
    re.compile(r"endpoint", re.IGNORECASE),
    # Common Framingham-style: "ex01_2" (exam 01, cohort 2)
    re.compile(r"_ex\d{1,2}_", re.IGNORECASE),
]

# Negative signals: table names that look temporal but aren't
# Use (?:^|[_\s-]) and (?:$|[_\s-]) instead of \b because \b treats _ as
# a word character, so "Cases" in "_Cases_" wouldn't match \bCases\b.
_TABLE_NEGATIVE_PATTERNS = [
    re.compile(r"(?:^|[_\s-])cases?(?:$|[_\s-])", re.IGNORECASE),
    re.compile(r"(?:^|[_\s-])controls?(?:$|[_\s-])", re.IGNORECASE),
    re.compile(r"(?:^|[_\s-])stage\s*\d+(?:$|[_\s-])", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Variable-name patterns (case-insensitive)
# ---------------------------------------------------------------------------

_VAR_POSITIVE_PATTERNS = [
    re.compile(r"exam\d+[_.]", re.IGNORECASE),
    re.compile(r"v\d{2}[_.]", re.IGNORECASE),
    re.compile(r"visit\d+", re.IGNORECASE),
    re.compile(r"_ex\d{1,2}$", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Time-point extraction from descriptions and table names
# ---------------------------------------------------------------------------

_TIMEPOINT_PATTERNS = [
    re.compile(r"(Exam\s*\d+)", re.IGNORECASE),
    re.compile(r"(Visit\s*\d+)", re.IGNORECASE),
    re.compile(r"(Wave\s*\d+)", re.IGNORECASE),
    re.compile(r"(Year\s*\d+)", re.IGNORECASE),
    re.compile(r"(Baseline)", re.IGNORECASE),
    re.compile(r"(Follow[\s-]?up\s*\d*)", re.IGNORECASE),
]

# Detect which kind of longitudinal pattern it is
_PATTERN_TYPE_MAP = [
    (re.compile(r"exam", re.IGNORECASE), "exam"),
    (re.compile(r"visit", re.IGNORECASE), "visit"),
    (re.compile(r"wave", re.IGNORECASE), "wave"),
    (re.compile(r"follow", re.IGNORECASE), "follow-up"),
    (re.compile(r"year", re.IGNORECASE), "year"),
    (re.compile(r"baseline|endpoint", re.IGNORECASE), "study-phase"),
    (re.compile(r"_ex\d", re.IGNORECASE), "exam"),
]


@dataclass
class LongitudinalResult:
    """Result of longitudinal detection for a table."""

    is_longitudinal: bool
    pattern: str | None  # "exam", "visit", "wave", etc.
    time_point: str | None  # "Exam 29", "Visit 3", etc.


def detect_table_longitudinal(table_name: str) -> LongitudinalResult:
    """Detect whether a table name indicates longitudinal data collection.

    Args:
        table_name: The table name to analyze.

    Returns:
        LongitudinalResult with detection outcome.
    """
    # Check negative signals first — they override positive matches
    for pat in _TABLE_NEGATIVE_PATTERNS:
        if pat.search(table_name):
            return LongitudinalResult(
                is_longitudinal=False, pattern=None, time_point=None
            )

    # Check positive signals
    for pat in _TABLE_POSITIVE_PATTERNS:
        if pat.search(table_name):
            pattern_type = _get_pattern_type(table_name)
            time_point = _extract_time_point(table_name)
            return LongitudinalResult(
                is_longitudinal=True,
                pattern=pattern_type,
                time_point=time_point,
            )

    return LongitudinalResult(is_longitudinal=False, pattern=None, time_point=None)


def detect_variable_longitudinal(
    var_name: str, var_description: str
) -> LongitudinalResult:
    """Detect whether a variable name/description indicates a time point.

    Args:
        var_name: The variable name.
        var_description: The variable description.

    Returns:
        LongitudinalResult with detection outcome.
    """
    # Check variable name patterns
    for pat in _VAR_POSITIVE_PATTERNS:
        if pat.search(var_name):
            pattern_type = _get_pattern_type(var_name)
            time_point = _extract_time_point(var_description) or _extract_time_point(
                var_name
            )
            return LongitudinalResult(
                is_longitudinal=True,
                pattern=pattern_type,
                time_point=time_point,
            )

    # Check description for time point references
    if var_description:
        time_point = _extract_time_point(var_description)
        if time_point:
            return LongitudinalResult(
                is_longitudinal=True,
                pattern=_get_pattern_type(var_description),
                time_point=time_point,
            )

    return LongitudinalResult(is_longitudinal=False, pattern=None, time_point=None)


def detect_study_longitudinal_concepts(
    tables: list[dict],
) -> set[str]:
    """Identify concepts that appear across multiple longitudinal tables.

    A concept is flagged as longitudinal if it appears in 2+ tables
    that have longitudinal table-name patterns.

    Args:
        tables: List of classified table dicts (with "concepts" and
                "isLongitudinal" fields).

    Returns:
        Set of concept names that are longitudinal.
    """
    concept_longitudinal_tables: dict[str, int] = {}

    for table in tables:
        if not table.get("isLongitudinal"):
            continue
        for concept in table.get("concepts", []):
            concept_longitudinal_tables[concept] = (
                concept_longitudinal_tables.get(concept, 0) + 1
            )

    return {c for c, count in concept_longitudinal_tables.items() if count >= 2}


def _get_pattern_type(text: str) -> str | None:
    """Determine the type of longitudinal pattern in a string.

    Args:
        text: Text to analyze.

    Returns:
        Pattern type string or None.
    """
    for pat, ptype in _PATTERN_TYPE_MAP:
        if pat.search(text):
            return ptype
    return None


def _extract_time_point(text: str) -> str | None:
    """Extract a human-readable time point from text.

    Args:
        text: Text to search (table name or variable description).

    Returns:
        Time point string (e.g., "Exam 29") or None.
    """
    for pat in _TIMEPOINT_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None
