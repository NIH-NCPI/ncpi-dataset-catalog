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

    def query_variables(
        self,
        concepts: list[str] | None = None,
        limit: int = 500,
        study_ids: set[str] | None = None,
        variable_names: set[str] | None = None,
    ) -> tuple[list[dict], int]:
        """Return variables matching concepts and/or study constraints."""
        ...

    def list_variables_for_concept(
        self, concept_id: str, limit: int = 200
    ) -> list[dict]:
        """Return distinct variables under a concept with descriptions."""
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
        self._conn.execute(
            "CREATE TABLE variables ("
            "  concept VARCHAR,"
            "  concept_lower VARCHAR,"
            "  cui VARCHAR,"
            "  concept_ids_closure VARCHAR[],"
            "  dataset_id VARCHAR,"
            "  description VARCHAR,"
            "  phv_id VARCHAR,"
            "  study_id VARCHAR,"
            "  table_name VARCHAR,"
            "  variable_name VARCHAR"
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

    def load_variables_batch(
        self,
        rows: list[
            tuple[str, str, str, str, str, str, str, str, str, str]
        ],
    ) -> None:
        """Batch-insert variable records via CSV COPY.

        Each row is (concept, concept_lower, cui, concept_ids_closure_json,
        dataset_id, description, phv_id, study_id, table_name, variable_name).

        DuckDB auto-casts JSON array strings to the native VARCHAR[] column
        during CSV COPY.
        """
        if not rows:
            return
        self._copy_csv("variables", rows)

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
        self._conn.execute(
            "CREATE INDEX idx_var_concept ON variables (concept_lower)"
        )
        self._conn.execute(
            "CREATE INDEX idx_var_study ON variables (study_id)"
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
            self._conn.execute(
                "CREATE TABLE export_db.variables "
                "AS SELECT * FROM variables"
            )
            # DuckDB doesn't support schema-qualified CREATE INDEX names,
            # so switch context to the attached DB for index creation.
            self._conn.execute("USE export_db")
            self._conn.execute(
                "CREATE INDEX idx_sfv "
                "ON study_facet_values (facet, value_lower)"
            )
            self._conn.execute(
                "CREATE INDEX idx_var_concept "
                "ON variables (concept_lower)"
            )
            self._conn.execute(
                "CREATE INDEX idx_var_study "
                "ON variables (study_id)"
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
        if not include and not exclude:
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

        if not where_clauses and not exclude:
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

    def query_variables(
        self,
        concepts: list[str] | None = None,
        limit: int = 500,
        study_ids: set[str] | None = None,
        variable_names: set[str] | None = None,
    ) -> tuple[list[dict], int]:
        """Return variables matching concept names and/or study IDs.

        Searches against concept_ids_closure (native VARCHAR[] of all
        ancestor concept_ids) so that querying a parent concept returns
        variables tagged with any descendant.

        Args:
            concepts: Canonical concept names to match (OR-ed). If None,
                all concepts are included (filtered by study_ids).
            limit: Maximum number of variable rows to return.
            study_ids: If provided, restrict results to these studies.
            variable_names: If provided, restrict to these variable names
                (case-insensitive).

        Returns:
            Tuple of (variable dicts, total count before LIMIT).
        """
        empty: tuple[list[dict], int] = ([], 0)
        if not concepts and not study_ids:
            return empty
        # Empty set means "filter matched nothing" — no variables can match.
        if study_ids is not None and not study_ids:
            return empty
        if variable_names is not None and not variable_names:
            return empty
        params: list[str] = []
        clauses: list[str] = []
        if concepts:
            # Search against ISA closure: a variable matches if any
            # concept in its closure array matches any requested concept.
            closure_clauses = []
            for c in concepts:
                closure_clauses.append(
                    "list_contains(v.concept_ids_closure, ?)"
                )
                params.append(c.lower())
            clauses.append(f"({' OR '.join(closure_clauses)})")
        if study_ids is not None:
            study_ph = ", ".join("?" for _ in study_ids)
            clauses.append(f"v.study_id IN ({study_ph})")
            params.extend(study_ids)
        if variable_names is not None:
            var_ph = ", ".join("?" for _ in variable_names)
            clauses.append(f"LOWER(v.variable_name) IN ({var_ph})")
            params.extend(n.lower() for n in variable_names)
        where = " AND ".join(clauses)
        # Get total count before applying LIMIT.
        count_sql = (
            "SELECT COUNT(*) FROM variables v "
            f"WHERE {where}"  # noqa: S608
        )
        total = self._conn.execute(count_sql, params).fetchone()[0]

        sql = (
            "SELECT v.concept, v.cui, v.dataset_id, v.description, v.phv_id,"
            "  v.study_id, v.table_name, v.variable_name,"
            "  json_extract_string(s.raw_json, '$.title') AS study_title "
            "FROM variables v "
            "LEFT JOIN studies s ON v.study_id = s.db_gap_id "
            f"WHERE {where} "  # noqa: S608
            "ORDER BY v.study_id, v.concept, v.variable_name "
            f"LIMIT {limit}"
        )
        rows = self._conn.execute(sql, params).fetchall()
        cols = [
            "concept", "cui", "datasetId", "description", "phvId",
            "studyId", "tableName", "variableName", "studyTitle",
        ]
        return [dict(zip(cols, row)) for row in rows], total

    def list_variables_for_concept(
        self, concept_id: str, limit: int = 200
    ) -> list[dict]:
        """Return distinct variables under a concept with descriptions.

        Searches against concept_ids_closure so that querying a parent concept
        returns variables tagged with any descendant.

        Args:
            concept_id: Concept to list variables for.
            limit: Maximum number of distinct variables to return.

        Returns:
            List of dicts with variable_name and description.
        """
        sql = (
            "SELECT DISTINCT variable_name, description "
            "FROM variables "
            "WHERE list_contains(concept_ids_closure, ?) "  # noqa: S608
            "ORDER BY variable_name "
            f"LIMIT {limit}"
        )
        rows = self._conn.execute(sql, [concept_id.lower()]).fetchall()
        return [{"description": row[1], "variable_name": row[0]} for row in rows]

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
