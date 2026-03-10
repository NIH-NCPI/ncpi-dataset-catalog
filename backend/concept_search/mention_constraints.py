"""Side-effect-free helpers for expanding mentions into query constraints.

Pure functions that convert resolved mentions into facet/value constraint
tuples suitable for the store layer.  No FastAPI, no I/O, no logging.
"""

from __future__ import annotations

from .consent_logic import TAG_TO_MODIFIER, expand_consent_tags, resolve_disease_name
from .index import ConceptIndex
from .models import Facet, ResolvedMention


def infer_consent_scope(
    mentions: list[ResolvedMention],
) -> tuple[str, str | None]:
    """Infer consent scope from sibling focus mentions.

    Scans ALL FOCUS mentions for disease context — tries both resolved
    values and original_text to maximise disease detection.  Returns a
    (scope, disease) tuple where scope is "general", "health", or "disease".

    Args:
        mentions: All resolved mentions in the current query.

    Returns:
        Tuple of (scope, disease_abbrev_or_none).
    """
    has_focus = False
    for m in mentions:
        if m.facet != Facet.FOCUS:
            continue
        has_focus = True
        # Try resolved values first, then original_text
        for val in m.values:
            disease = resolve_disease_name(val)
            if disease:
                return ("disease", disease)
        disease = resolve_disease_name(m.original_text)
        if disease:
            return ("disease", disease)
    # Focus exists but no disease match → health scope
    if has_focus:
        return ("health", None)
    return ("general", None)


def split_mentions(
    mentions: list[ResolvedMention],
    index: ConceptIndex | None = None,
) -> tuple[list[tuple[Facet, list[str]]], list[tuple[Facet, list[str]]]]:
    """Split mentions into include and exclude constraint lists.

    For CONSENT_CODE mentions with tag values (``no-*`` or ``explicit:*``),
    expands tags into actual consent codes using scope inferred from sibling
    focus mentions.

    Each mention becomes its own constraint tuple (AND between mentions,
    OR within a mention's values).

    Args:
        mentions: All resolved mentions.
        index: ConceptIndex for consent code expansion. When ``None``,
            consent tag expansion is skipped.

    Returns:
        Tuple of (include_constraints, exclude_constraints).
    """
    include: list[tuple[Facet, list[str]]] = []
    exclude: list[tuple[Facet, list[str]]] = []

    # Pre-compute consent expansion inputs (lazy — only when needed)
    consent_scope: tuple[str, str | None] | None = None
    all_codes: list[str] | None = None

    for mention in mentions:
        values = mention.values
        # Expand consent tags into actual codes
        if (
            mention.facet == Facet.CONSENT_CODE
            and index is not None
            and values is not None
        ):
            has_tags = any(
                v in TAG_TO_MODIFIER or v.startswith("explicit:") for v in values
            )
            if has_tags or values == []:
                if consent_scope is None:
                    consent_scope = infer_consent_scope(mentions)
                if all_codes is None:
                    all_codes = [
                        m.value for m in index.list_facet_values("consentCode")
                    ]
                scope, disease = consent_scope
                values = expand_consent_tags(
                    all_codes, values, scope=scope, disease=disease
                )
                # If expansion yields nothing (e.g. all codes excluded),
                # use a sentinel so the constraint stays active and returns
                # zero results rather than silently broadening the query.
                if not values:
                    values = ["__NO_MATCH__"]
        if values:
            target = exclude if mention.exclude else include
            target.append((mention.facet, values))
    return include, exclude
