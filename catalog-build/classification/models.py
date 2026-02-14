"""Data models for the variable classification pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ParsedTable:
    """A parsed dbGaP dataset table with its variables."""

    study_id: str
    dataset_id: str
    table_name: str
    study_name: str
    description: str
    variables: list[str]
    variable_count: int
    file_path: str

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ParsedTable:
        """Create from a dict (e.g. loaded from JSON cache)."""
        return cls(**d)


@dataclass
class Rule:
    """A classification rule that matches tables by name or description."""

    match_field: str  # "tableName" or "description"
    pattern: str  # regex pattern
    concept: str  # e.g. "accelerometer-wearable-data"
    domain: str  # e.g. "Physical Activity"
    rationale: str | None = None
    description: str | None = None  # example table description(s) for human auditing

    @classmethod
    def from_dict(cls, d: dict) -> Rule:
        """Create from a rule entry in a JSON rule file."""
        match = d["match"]
        match_field, pattern = next(iter(match.items()))
        return cls(
            match_field=match_field,
            pattern=pattern,
            concept=d["concept"],
            domain=d["domain"],
            rationale=d.get("rationale"),
            description=d.get("description"),
        )


@dataclass
class RuleFile:
    """A collection of rules for a study (or the default rule set)."""

    study_id: str
    study_name: str
    rules: list[Rule]

    @classmethod
    def load(cls, path: Path) -> RuleFile:
        """Load a rule file from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            study_id=data["studyId"],
            study_name=data["studyName"],
            rules=[Rule.from_dict(r) for r in data["rules"]],
        )


@dataclass
class Classification:
    """A classification result: a table assigned to a concept."""

    study_id: str
    dataset_id: str
    table_name: str
    concept: str
    domain: str
    phase: int
    rule_source: str  # e.g. "phs000007:tableName:^t_physactf_"
    variable_count: int
    variables: list[str]

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)


@dataclass
class CoverageStats:
    """Coverage statistics for a single study."""

    study_id: str
    study_name: str
    total_tables: int
    classified_tables: int
    unclassified_tables: int
    total_variables: int
    classified_variables: int
    unclassified_variables: int
    classification_rate: float
    concepts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)
