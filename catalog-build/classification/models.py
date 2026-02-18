"""Data models for the variable classification pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass


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
