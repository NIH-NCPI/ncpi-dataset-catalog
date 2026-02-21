"""Swappable study-store backends.

Provides a ``StudyStore`` protocol and a ``DuckDBStore`` implementation.
Future backends (e.g. OpenSearch) implement the same protocol.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Facet


@runtime_checkable
class StudyStore(Protocol):
    """Protocol for study-lookup backends.

    Semantic contract:

    - Each constraint is a ``(facet, values)`` tuple.
    - Within a constraint, values are **OR-ed** (match *any*).
    - Between constraints, results are **AND-ed** (match *all*).
    - Excluded constraints **subtract** matching studies from the result.
    """

    def query_studies(
        self,
        include: list[tuple[Facet, list[str]]],
        exclude: list[tuple[Facet, list[str]]] | None = None,
    ) -> list[dict]:
        """Return studies matching *include* minus *exclude*."""
        ...


class DuckDBStore:
    """In-memory DuckDB implementation of ``StudyStore``.

    Supports saving to / loading from a ``.duckdb`` file so that
    subsequent startups skip JSON parsing entirely.
    """

    def __init__(self, *, db_path: str = ":memory:", read_only: bool = False) -> None:
        import duckdb

        self._conn = duckdb.connect(db_path, read_only=read_only)

    @classmethod
    def create_empty(cls) -> DuckDBStore:
        """Create a new in-memory store with empty tables."""
        store = cls()
        store._init_schema()
        return store

    @classmethod
    def load_from_file(cls, path: str | Path) -> DuckDBStore:
        """Open a previously saved DuckDB file (read-only)."""
        return cls(db_path=str(path), read_only=True)

    # -- schema ---------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE studies ("
            "  db_gap_id VARCHAR PRIMARY KEY,"
            "  raw_json VARCHAR"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE study_facet_values ("
            "  db_gap_id VARCHAR,"
            "  facet VARCHAR,"
            "  value VARCHAR,"
            "  value_lower VARCHAR"
            ")"
        )

    # -- bulk loading ---------------------------------------------------------

    def load_study(self, db_gap_id: str, study: dict) -> None:
        """Insert a study record with its full JSON."""
        self._conn.execute(
            "INSERT INTO studies VALUES (?, ?)",
            [db_gap_id, json.dumps(study)],
        )

    def load_facet_value(
        self, db_gap_id: str, facet: Facet, value: str
    ) -> None:
        """Insert a facet value for a study."""
        self._conn.execute(
            "INSERT INTO study_facet_values VALUES (?, ?, ?, ?)",
            [db_gap_id, facet.value, value, value.lower()],
        )

    def load_studies_batch(self, rows: list[tuple[str, dict]]) -> None:
        """Batch-insert study records via CSV COPY."""
        if not rows:
            return
        self._copy_csv(
            "studies",
            [(sid, json.dumps(study)) for sid, study in rows],
        )

    def load_facet_values_batch(
        self, rows: list[tuple[str, str, str, str]]
    ) -> None:
        """Batch-insert facet values via CSV COPY.

        Each row is (db_gap_id, facet_value, value, value_lower).
        """
        if not rows:
            return
        self._copy_csv("study_facet_values", rows)

    def _copy_csv(
        self, table: str, rows: list[tuple[str, ...]]
    ) -> None:
        """Write rows to a temp CSV and COPY into the table."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(row)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.write(buf.getvalue())
            tmp = f.name
        try:
            self._conn.execute(
                f"COPY {table} FROM '{tmp}' (FORMAT CSV, HEADER false)"  # noqa: S608
            )
        finally:
            os.unlink(tmp)

    def finalize(self) -> None:
        """Create indexes after bulk loading is complete."""
        self._conn.execute(
            "CREATE INDEX idx_sfv ON study_facet_values (facet, value_lower)"
        )

    # -- persistence ----------------------------------------------------------

    def save_to_file(self, path: str | Path) -> None:
        """Export the in-memory database to a file."""
        path = str(path)
        tmp = path + ".tmp"
        # Remove stale temp file if it exists
        if os.path.exists(tmp):
            os.unlink(tmp)
        self._conn.execute(f"ATTACH '{tmp}' AS export_db")
        try:
            self._conn.execute(
                "CREATE TABLE export_db.studies AS SELECT * FROM studies"
            )
            self._conn.execute(
                "CREATE TABLE export_db.study_facet_values "
                "AS SELECT * FROM study_facet_values"
            )
            # DuckDB doesn't support schema-qualified CREATE INDEX names,
            # so switch context to the attached DB for index creation.
            self._conn.execute("USE export_db")
            self._conn.execute(
                "CREATE INDEX idx_sfv "
                "ON study_facet_values (facet, value_lower)"
            )
        finally:
            self._conn.execute("USE memory")
            self._conn.execute("DETACH export_db")
        os.rename(tmp, path)

    # -- query ----------------------------------------------------------------

    def query_studies(
        self,
        include: list[tuple[Facet, list[str]]],
        exclude: list[tuple[Facet, list[str]]] | None = None,
    ) -> list[dict]:
        """Query studies using SQL-based faceted search."""
        if not include:
            return []

        where_clauses: list[str] = []
        params: list[str] = []

        # Include: each constraint is AND-ed; values within are OR-ed
        for facet, values in include:
            if not values:
                continue
            placeholders = ", ".join("?" for _ in values)
            where_clauses.append(
                f"s.db_gap_id IN ("
                f"SELECT db_gap_id FROM study_facet_values "
                f"WHERE facet = ? AND value_lower IN ({placeholders})"
                f")"
            )
            params.append(facet.value)
            params.extend(v.lower() for v in values)

        if not where_clauses:
            return []

        # Exclude: each constraint subtracts matching studies
        if exclude:
            for facet, values in exclude:
                if not values:
                    continue
                placeholders = ", ".join("?" for _ in values)
                where_clauses.append(
                    f"s.db_gap_id NOT IN ("
                    f"SELECT db_gap_id FROM study_facet_values "
                    f"WHERE facet = ? AND value_lower IN ({placeholders})"
                    f")"
                )
                params.append(facet.value)
                params.extend(v.lower() for v in values)

        sql = (
            "SELECT s.raw_json FROM studies s "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY s.db_gap_id"
        )

        rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_facet_value_counts(self) -> list[tuple[str, str, int]]:
        """Return (facet, value, study_count) for all facet values.

        Used to rebuild the concept index from a cached database.
        """
        rows = self._conn.execute(
            "SELECT facet, value, COUNT(DISTINCT db_gap_id) AS cnt "
            "FROM study_facet_values "
            "GROUP BY facet, value "
            "ORDER BY facet, cnt DESC"
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    @property
    def study_count(self) -> int:
        """Total number of studies in the store."""
        row = self._conn.execute("SELECT COUNT(*) FROM studies").fetchone()
        return row[0] if row else 0
