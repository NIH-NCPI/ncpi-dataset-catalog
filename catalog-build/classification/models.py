"""Data models for the variable classification pipeline."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field, model_validator


@dataclass
class ParsedTable:
    """A parsed dbGaP dataset table with its variables."""

    study_id: str
    dataset_id: str
    table_name: str
    study_name: str
    description: str
    variables: list[dict[str, str]]  # [{"name": "VAR", "description": "..."}]
    variable_count: int
    file_path: str

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ParsedTable:
        """Create from a dict (e.g. loaded from JSON cache)."""
        return cls(**d)


# ---------------------------------------------------------------------------
# V2 models — Pydantic output models for reorganize_concepts.py
# ---------------------------------------------------------------------------

# Title Case validation: allows lowercase prepositions/articles and words
# starting with digits or special characters (matching UMLS/SNOMED conventions).
_TITLE_CASE_EXEMPT = {"a", "an", "and", "at", "by", "for", "in", "of", "on",
                      "or", "the", "to", "vs", "with"}


def _is_title_case(name: str) -> bool:
    """Check if a concept name follows Title Case conventions.

    Allows lowercase prepositions/articles and words starting with
    digits or special characters.

    Args:
        name: Concept name to check.

    Returns:
        True if the name follows Title Case.
    """
    words = re.split(r"[\s/]+", name)
    for i, word in enumerate(words):
        # Strip leading punctuation like "(" for checking
        stripped = word.lstrip("(-")
        if not stripped or stripped[0].isdigit():
            continue
        # First word must be capitalized; others can be exempt
        if i == 0:
            if stripped[0].islower():
                return False
        elif stripped.lower() in _TITLE_CASE_EXEMPT:
            continue
        elif stripped[0].islower():
            return False
    return True


# ---------------------------------------------------------------------------
# Tree node (used for serialization to hierarchy JSON, not LLM output)
# ---------------------------------------------------------------------------


class ConceptNode(BaseModel):
    """A node in the variable-depth concept tree."""

    children: list[ConceptNode] = Field(
        default_factory=list,
        description="Child concepts (more specific types of this concept)",
    )
    concept: str = Field(description="Canonical concept name in Title Case")


def _collect_tree_concepts(nodes: list[ConceptNode], out: set[str]) -> None:
    """Recursively collect all concept names from tree nodes.

    Args:
        nodes: List of tree nodes to traverse.
        out: Set to add concept names to.
    """
    for node in nodes:
        out.add(node.concept)
        _collect_tree_concepts(node.children, out)


def find_single_child_nodes(nodes: list[ConceptNode]) -> list[str]:
    """Find nodes that have exactly one child (soft warning, not error).

    Args:
        nodes: List of tree nodes to check recursively.

    Returns:
        List of concept names that have only one child.
    """
    violations: list[str] = []
    for node in nodes:
        if len(node.children) == 1:
            violations.append(node.concept)
        violations.extend(find_single_child_nodes(node.children))
    return violations


# ---------------------------------------------------------------------------
# Flat representation for LLM output
# ---------------------------------------------------------------------------


class ConceptPlacement(BaseModel):
    """A concept with its parent reference (flat representation for LLM)."""

    concept: str = Field(description="Concept name in Title Case")
    parent: str | None = Field(
        default=None,
        description="Parent concept name, or null for root-level concepts",
    )


def _validate_concept_placements(placements: list[ConceptPlacement]) -> set[str]:
    """Shared validation for flat concept lists.

    Checks for duplicates, Title Case, casing duplicates, and valid parent refs.

    Args:
        placements: List of concept placements to validate.

    Returns:
        Set of concept names.
    """
    # Check for duplicate concept names
    seen: set[str] = set()
    for p in placements:
        if p.concept in seen:
            raise ValueError(f"Duplicate concept: '{p.concept}'.")
        seen.add(p.concept)
    concept_names = seen

    # No self-parenting
    for p in placements:
        if p.parent is not None and p.parent == p.concept:
            raise ValueError(
                f"Concept '{p.concept}' lists itself as its own parent."
            )

    # Parent references must point to concepts in the list
    for p in placements:
        if p.parent is not None and p.parent not in concept_names:
            raise ValueError(
                f"Parent '{p.parent}' for concept '{p.concept}' "
                f"not found in concepts list."
            )

    # Each concept appears once (already checked via duplicate check above),
    # and each has at most one parent field — the flat list structure enforces
    # single-parent by construction (one row per concept, one parent field).

    return concept_names


def build_tree_from_placements(
    placements: list[ConceptPlacement],
) -> list[ConceptNode]:
    """Convert flat ConceptPlacement list to a ConceptNode tree.

    Args:
        placements: Flat list of concept-parent pairs.

    Returns:
        List of root ConceptNode objects.
    """
    nodes: dict[str, ConceptNode] = {}
    for p in placements:
        nodes[p.concept] = ConceptNode(concept=p.concept)

    roots: list[ConceptNode] = []
    for p in placements:
        if p.parent is None:
            roots.append(nodes[p.concept])
        elif p.parent in nodes:
            nodes[p.parent].children.append(nodes[p.concept])

    return roots


# ---------------------------------------------------------------------------
# Synonym mapping
# ---------------------------------------------------------------------------


class SynonymMapping(BaseModel):
    """A single synonym-to-canonical mapping."""

    canonical: str = Field(description="The canonical concept name to keep")
    synonym: str = Field(description="The synonym concept name to merge")


# ---------------------------------------------------------------------------
# LLM output models (flat concepts + COT reasoning)
# ---------------------------------------------------------------------------


class MidLevelReorgResult(BaseModel):
    """LLM output for reorganizing one mid-level's concepts (single-pass).

    Uses flat concept-parent pairs instead of nested tree for simpler output.
    The reasoning field enables chain-of-thought before committing to structure.

    Validators ensure:
    - All concept names are Title Case
    - No casing duplicates
    - Synonym targets exist in the concepts list
    - Parent references are valid
    """

    reasoning: str = Field(
        description=(
            "Brief analysis: identify synonym groups and explain "
            "the hierarchy structure"
        ),
    )
    synonyms: list[SynonymMapping] = Field(
        default_factory=list,
        description="Concepts to merge (old name → canonical name)",
    )
    concepts: list[ConceptPlacement] = Field(
        description="All canonical concepts with parent references (flat list)",
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> MidLevelReorgResult:
        """Validate concept + synonym consistency."""
        concept_names = _validate_concept_placements(self.concepts)

        # Synonym targets must exist in concepts
        for syn in self.synonyms:
            if syn.canonical not in concept_names:
                raise ValueError(
                    f"Synonym target '{syn.canonical}' for "
                    f"'{syn.synonym}' not found in concepts."
                )

        # No synonym source in concepts
        synonym_sources = {s.synonym for s in self.synonyms}
        overlap = synonym_sources & concept_names
        if overlap:
            raise ValueError(
                f"These appear both as synonym sources and in "
                f"concepts: {overlap}. A concept should be in the "
                f"concepts list OR be a synonym, not both."
            )

        # No duplicate synonym sources
        source_counts = Counter(s.synonym for s in self.synonyms)
        dupes = {k: v for k, v in source_counts.items() if v > 1}
        if dupes:
            raise ValueError(
                f"Duplicate synonym sources: {dupes}. Each concept "
                f"should be mapped to exactly one canonical name."
            )

        return self

    def get_all_concepts(self) -> set[str]:
        """Return all concept names.

        Returns:
            Set of concept names.
        """
        return {p.concept for p in self.concepts}

    def get_synonym_map(self) -> dict[str, str]:
        """Return synonym-to-canonical mapping as a dict.

        Returns:
            Dict mapping synonym names to canonical names.
        """
        return {s.synonym: s.canonical for s in self.synonyms}

    def build_tree(self) -> list[ConceptNode]:
        """Build ConceptNode tree from flat placements.

        Returns:
            List of root ConceptNode objects.
        """
        return build_tree_from_placements(self.concepts)


class SynonymOnlyResult(BaseModel):
    """LLM output for synonym detection (pass 1 of two-pass pipeline)."""

    reasoning: str = Field(
        description="Brief analysis of which concepts are synonyms and why",
    )
    synonyms: list[SynonymMapping] = Field(
        default_factory=list,
        description="Concepts to merge (old name → canonical name)",
    )

    @model_validator(mode="after")
    def validate_synonyms(self) -> SynonymOnlyResult:
        """Validate synonym consistency."""
        for s in self.synonyms:
            if s.synonym == s.canonical:
                raise ValueError(f"Synonym '{s.synonym}' maps to itself.")
        source_counts = Counter(s.synonym for s in self.synonyms)
        dupes = {k: v for k, v in source_counts.items() if v > 1}
        if dupes:
            raise ValueError(
                f"Duplicate synonym sources: {dupes}. Each concept "
                f"should be mapped to exactly one canonical name."
            )
        return self


class TreeOnlyResult(BaseModel):
    """LLM output for tree building (pass 2 of two-pass pipeline)."""

    reasoning: str = Field(
        description="Brief analysis of the is_a hierarchy structure",
    )
    concepts: list[ConceptPlacement] = Field(
        description="All concepts with parent references (flat list)",
    )

    @model_validator(mode="after")
    def validate_tree(self) -> TreeOnlyResult:
        """Validate concept placement consistency."""
        _validate_concept_placements(self.concepts)
        return self

    def get_all_concepts(self) -> set[str]:
        """Return all concept names.

        Returns:
            Set of concept names.
        """
        return {p.concept for p in self.concepts}

    def build_tree(self) -> list[ConceptNode]:
        """Build ConceptNode tree from flat placements.

        Returns:
            List of root ConceptNode objects.
        """
        return build_tree_from_placements(self.concepts)
