"""Load UMLS Metathesaurus RRF files into a local SQLite database.

Reads the key RRF files (MRCONSO, MRDEF, MRSTY, MRREL) from an extracted
UMLS download and loads them into a single SQLite database with indexes
optimized for concept lookup, vocabulary crosswalks, and semantic type
filtering.

Prerequisites:
    1. Download the UMLS Metathesaurus Full Subset from
       https://www.nlm.nih.gov/research/umls/licensedcontent/umlsknowledgesources.html
    2. Extract the zip — the RRF files live under a path like:
       2025AB/META/MRCONSO.RRF

Usage:
    python load_umls.py /path/to/2025AB/META
    python load_umls.py /path/to/2025AB/META --output umls.db
    python load_umls.py /path/to/2025AB/META --english-only
    python load_umls.py /path/to/2025AB/META --tables MRCONSO MRSTY
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from pathlib import Path

# Bump field size limit — MRDEF and MRREL have some very long rows
csv.field_size_limit(sys.maxsize)

# ── Schema definitions ───────────────────────────────────────────────
# Each entry: (table_name, columns, indexes)
# Columns are in the order they appear in the RRF file.
# Indexes are (index_name, column_expression) pairs.

TABLES: dict[str, dict] = {
    "MRCONSO": {
        "columns": [
            "CUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF",
            "AUI", "SAUI", "SCUI", "SDUI", "SAB", "TTY", "CODE",
            "STR", "SRL", "SUPPRESS", "CVF",
        ],
        "indexes": [
            ("idx_mrconso_cui", "CUI"),
            ("idx_mrconso_aui", "AUI"),
            ("idx_mrconso_sab_code", "SAB, CODE"),
            ("idx_mrconso_cui_sab", "CUI, SAB"),
            ("idx_mrconso_str", "STR"),
        ],
    },
    "MRDEF": {
        "columns": [
            "CUI", "AUI", "ATUI", "SATUI", "SAB", "DEF", "SUPPRESS", "CVF",
        ],
        "indexes": [
            ("idx_mrdef_cui", "CUI"),
            ("idx_mrdef_aui", "AUI"),
        ],
    },
    "MRSTY": {
        "columns": [
            "CUI", "TUI", "STN", "STY", "ATUI", "CVF",
        ],
        "indexes": [
            ("idx_mrsty_cui", "CUI"),
            ("idx_mrsty_tui", "TUI"),
        ],
    },
    "MRREL": {
        "columns": [
            "CUI1", "AUI1", "STYPE1", "REL", "CUI2", "AUI2", "STYPE2",
            "RELA", "RUI", "SRUI", "SAB", "SL", "RG", "DIR",
            "SUPPRESS", "CVF",
        ],
        "indexes": [
            ("idx_mrrel_cui1", "CUI1"),
            ("idx_mrrel_cui2", "CUI2"),
            ("idx_mrrel_sab_rel", "SAB, REL"),
        ],
    },
    "MRSAB": {
        "columns": [
            "VCUI", "RCUI", "VSAB", "RSAB", "SON", "SF", "SVER",
            "VSTART", "VEND", "IMETA", "RMETA", "SLC", "SCC", "SRL",
            "TFR", "CFR", "CXTY", "TTYL", "ATNL", "LAT", "CENC",
            "CURVER", "SABIN", "SSN", "SCIT",
        ],
        "indexes": [
            ("idx_mrsab_rsab", "RSAB"),
        ],
    },
}

OUTPUT_DEFAULT = "umls.db"


def load_rrf(
    db: sqlite3.Connection,
    rrf_path: Path,
    table_name: str,
    schema: dict,
    *,
    english_only: bool = False,
) -> int:
    """Load a single RRF file into a SQLite table.

    Returns the number of rows inserted.
    """
    columns = schema["columns"]
    ncols = len(columns)

    col_defs = ", ".join(f"{c} TEXT" for c in columns)
    db.execute(f"DROP TABLE IF EXISTS {table_name}")
    db.execute(f"CREATE TABLE {table_name} ({col_defs})")

    # Find LAT column index for english-only filtering
    lat_idx = columns.index("LAT") if "LAT" in columns else None

    placeholders = ", ".join("?" * ncols)
    insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"

    rows = 0
    batch: list[tuple] = []
    batch_size = 50_000

    with open(rrf_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        for row in reader:
            # RRF files have a trailing pipe, producing an extra empty field
            values = row[:ncols]
            if len(values) < ncols:
                values.extend([""] * (ncols - len(values)))

            if english_only and lat_idx is not None and values[lat_idx] != "ENG":
                continue

            batch.append(tuple(values))
            if len(batch) >= batch_size:
                db.executemany(insert_sql, batch)
                rows += len(batch)
                batch.clear()

    if batch:
        db.executemany(insert_sql, batch)
        rows += len(batch)

    db.commit()
    return rows


def create_indexes(db: sqlite3.Connection, table_name: str, schema: dict) -> None:
    """Create indexes for a table."""
    for idx_name, idx_cols in schema["indexes"]:
        db.execute(f"CREATE INDEX {idx_name} ON {table_name} ({idx_cols})")
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load UMLS RRF files into SQLite.",
    )
    parser.add_argument(
        "meta_dir",
        type=Path,
        help="Path to extracted META directory containing RRF files",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(OUTPUT_DEFAULT),
        help=f"Output SQLite database path (default: {OUTPUT_DEFAULT})",
    )
    parser.add_argument(
        "--english-only",
        action="store_true",
        help="Only load English-language entries (cuts MRCONSO size roughly in half)",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=list(TABLES.keys()),
        default=list(TABLES.keys()),
        help="Which tables to load (default: all)",
    )
    args = parser.parse_args()

    meta_dir: Path = args.meta_dir
    if not meta_dir.is_dir():
        print(f"Error: {meta_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    db_path: Path = args.output
    print(f"Database: {db_path}")
    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-512000")  # 512 MB cache

    total_start = time.time()

    for table_name in args.tables:
        rrf_file = meta_dir / f"{table_name}.RRF"
        if not rrf_file.exists():
            print(f"  Skipping {table_name} — {rrf_file} not found")
            continue

        schema = TABLES[table_name]
        size_mb = rrf_file.stat().st_size / (1024 * 1024)
        print(f"  Loading {table_name}.RRF ({size_mb:.0f} MB)...", end=" ", flush=True)

        t0 = time.time()
        rows = load_rrf(db, rrf_file, table_name, schema, english_only=args.english_only)
        t_load = time.time() - t0
        print(f"{rows:,} rows in {t_load:.1f}s", end=" ", flush=True)

        t0 = time.time()
        create_indexes(db, table_name, schema)
        t_idx = time.time() - t0
        print(f"(indexes: {t_idx:.1f}s)")

    db.close()

    elapsed = time.time() - total_start
    db_size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"\nDone in {elapsed:.0f}s — {db_path} ({db_size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
