"""Convenience queries against the local UMLS SQLite database.

Provides common lookup patterns for concept resolution, vocabulary
crosswalks, and semantic type filtering.

Usage:
    python query_umls.py search "systolic blood pressure"
    python query_umls.py cui C0871470
    python query_umls.py crosswalk SNOMEDCT_US 271649006 --target LNC
    python query_umls.py semtype C0020538
    python query_umls.py vocabs
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_DEFAULT = "umls.db"


def connect(db_path: str) -> sqlite3.Connection:
    """Open the UMLS database read-only."""
    path = Path(db_path)
    if not path.exists():
        print(f"Error: {path} not found. Run load_umls.py first.", file=sys.stderr)
        sys.exit(1)
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def cmd_search(db: sqlite3.Connection, term: str, limit: int) -> None:
    """Search for concepts by name (case-insensitive substring match)."""
    rows = db.execute(
        """
        SELECT DISTINCT c.CUI, c.STR, c.SAB,
               COALESCE(s.STY, '') AS semantic_type
        FROM mrconso c
        LEFT JOIN mrsty s ON c.CUI = s.CUI
        WHERE c.STR LIKE ? AND c.LAT = 'ENG' AND c.SUPPRESS = 'N'
        ORDER BY length(c.STR), c.STR
        LIMIT ?
        """,
        (f"%{term}%", limit),
    ).fetchall()

    if not rows:
        print(f"No results for '{term}'")
        return

    print(f"{'CUI':<12} {'SAB':<16} {'Semantic Type':<30} STR")
    print("-" * 100)
    for r in rows:
        print(f"{r['CUI']:<12} {r['SAB']:<16} {r['semantic_type']:<30} {r['STR']}")


def cmd_cui(db: sqlite3.Connection, cui: str) -> None:
    """Look up all names and codes for a CUI."""
    cui = cui.upper()

    # Names across vocabularies
    rows = db.execute(
        """
        SELECT SAB, TTY, CODE, STR
        FROM mrconso WHERE CUI = ? AND LAT = 'ENG' AND SUPPRESS = 'N'
        ORDER BY SAB, TTY
        """,
        (cui,),
    ).fetchall()

    if not rows:
        print(f"CUI {cui} not found")
        return

    print(f"\n=== {cui} — Names & Codes ===\n")
    print(f"{'SAB':<16} {'TTY':<6} {'CODE':<20} STR")
    print("-" * 90)
    for r in rows:
        print(f"{r['SAB']:<16} {r['TTY']:<6} {r['CODE']:<20} {r['STR']}")

    # Semantic types
    stys = db.execute(
        "SELECT TUI, STY FROM mrsty WHERE CUI = ?", (cui,)
    ).fetchall()
    if stys:
        print(f"\n=== Semantic Types ===\n")
        for s in stys:
            print(f"  {s['TUI']}  {s['STY']}")

    # Definitions
    defs = db.execute(
        "SELECT SAB, DEF FROM mrdef WHERE CUI = ?", (cui,)
    ).fetchall()
    if defs:
        print(f"\n=== Definitions ===\n")
        for d in defs:
            print(f"  [{d['SAB']}] {d['DEF'][:200]}")


def cmd_crosswalk(
    db: sqlite3.Connection, source: str, code: str, target: str | None
) -> None:
    """Find codes in other vocabularies that share the same CUI."""
    # First resolve to CUI
    cui_row = db.execute(
        "SELECT CUI, STR FROM mrconso WHERE SAB = ? AND CODE = ? AND LAT = 'ENG' LIMIT 1",
        (source, code),
    ).fetchone()

    if not cui_row:
        print(f"No concept found for {source}:{code}")
        return

    cui = cui_row["CUI"]
    print(f"\n{source}:{code} -> {cui} ({cui_row['STR']})\n")

    query = """
        SELECT DISTINCT SAB, CODE, STR
        FROM mrconso
        WHERE CUI = ? AND SAB != ? AND LAT = 'ENG' AND SUPPRESS = 'N'
    """
    params: list = [cui, source]

    if target:
        query += " AND SAB = ?"
        params.append(target)

    query += " ORDER BY SAB, CODE"

    rows = db.execute(query, params).fetchall()
    if not rows:
        print("No crosswalk results")
        return

    print(f"{'SAB':<16} {'CODE':<20} STR")
    print("-" * 80)
    for r in rows:
        print(f"{r['SAB']:<16} {r['CODE']:<20} {r['STR']}")


def cmd_semtype(db: sqlite3.Connection, cui: str) -> None:
    """Show semantic types for a CUI."""
    cui = cui.upper()
    rows = db.execute(
        "SELECT TUI, STY FROM mrsty WHERE CUI = ?", (cui,)
    ).fetchall()
    if not rows:
        print(f"No semantic types for {cui}")
        return
    for r in rows:
        print(f"  {r['TUI']}  {r['STY']}")


def cmd_vocabs(db: sqlite3.Connection) -> None:
    """List all source vocabularies in the database."""
    rows = db.execute(
        """
        SELECT RSAB, SON, SRL
        FROM mrsab
        WHERE CURVER = 'Y'
        ORDER BY RSAB
        """
    ).fetchall()

    if not rows:
        # Fallback if MRSAB wasn't loaded
        rows = db.execute(
            "SELECT DISTINCT SAB FROM mrconso ORDER BY SAB"
        ).fetchall()
        for r in rows:
            print(r["SAB"] if isinstance(r, sqlite3.Row) else r[0])
        return

    print(f"{'SAB':<20} {'License':<8} Name")
    print("-" * 90)
    for r in rows:
        print(f"{r['RSAB']:<20} {r['SRL']:<8} {r['SON'][:60]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query local UMLS database.")
    parser.add_argument(
        "--db", default=DB_DEFAULT, help=f"Path to SQLite database (default: {DB_DEFAULT})",
    )

    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Search concepts by name")
    p_search.add_argument("term", help="Search term (substring match)")
    p_search.add_argument("--limit", type=int, default=25)

    p_cui = sub.add_parser("cui", help="Look up a CUI")
    p_cui.add_argument("cui", help="Concept Unique Identifier (e.g. C0020538)")

    p_xwalk = sub.add_parser("crosswalk", help="Vocabulary crosswalk")
    p_xwalk.add_argument("source", help="Source vocabulary (e.g. SNOMEDCT_US)")
    p_xwalk.add_argument("code", help="Source code (e.g. 38341003)")
    p_xwalk.add_argument("--target", help="Target vocabulary to filter to")

    p_sty = sub.add_parser("semtype", help="Semantic types for a CUI")
    p_sty.add_argument("cui")

    sub.add_parser("vocabs", help="List source vocabularies")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    db = connect(args.db)

    if args.command == "search":
        cmd_search(db, args.term, args.limit)
    elif args.command == "cui":
        cmd_cui(db, args.cui)
    elif args.command == "crosswalk":
        cmd_crosswalk(db, args.source, args.code, args.target)
    elif args.command == "semtype":
        cmd_semtype(db, args.cui)
    elif args.command == "vocabs":
        cmd_vocabs(db)

    db.close()


if __name__ == "__main__":
    main()
