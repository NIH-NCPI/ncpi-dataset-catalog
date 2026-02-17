"""CLI entry point for concept search."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from .index import get_index
from .models import Facet
from .pipeline import run_pipeline


def main() -> None:
    """Run the concept search CLI."""
    # Load .env from the backend directory (parent of this package)
    _backend_dir = Path(__file__).resolve().parent.parent
    load_dotenv(_backend_dir / ".env")

    parser = argparse.ArgumentParser(
        description="NCPI Concept Search — parse natural-language queries into faceted mentions"
    )
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--lookup",
        action="store_true",
        help="Also run deterministic study lookup after mention extraction",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override agent model (e.g. anthropic:claude-sonnet-4-5-20250929)",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(message)s")

    result = asyncio.run(run_pipeline(args.query, model=args.model))

    print("\n=== QueryModel ===")
    print(result.model_dump_json(indent=2))

    if args.lookup and result.mentions:
        print("\n=== Study Lookup ===")
        index = get_index()
        include: list[tuple[Facet, list[str]]] = []
        exclude: list[tuple[Facet, list[str]]] = []
        for mention in result.mentions:
            if mention.values:
                target = exclude if mention.exclude else include
                target.append((mention.facet, mention.values))

        studies = index.query_studies(include, exclude or None)
        print(f"Found {len(studies)} matching studies")
        for s in studies[:10]:
            print(f"  {s.get('dbGapId', '?'):12s} {s.get('title', '?')[:80]}")
        if len(studies) > 10:
            print(f"  ... and {len(studies) - 10} more")


if __name__ == "__main__":
    main()
