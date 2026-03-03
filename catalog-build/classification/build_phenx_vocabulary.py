#!/usr/bin/env python3
"""Build PhenX concept vocabulary from protocol metadata and variable cross-reference.

Reads:
- source/phenx/protocol_id_name.xls — protocol IDs and human-readable names
- source/phenx/Variable_cross_reference.xlsx — maps PhenX variables to dbGaP phv IDs
- source/phenx/protocol_descriptions.json — cached descriptions from phenxtoolkit.org

Produces: output/phenx-concept-vocabulary.json

Only includes protocols that have at least one dbGaP mapping (i.e., appear in
Variable_cross_reference.xlsx).

Usage:
    python build_phenx_vocabulary.py                # Build vocab (uses cached descriptions)
    python build_phenx_vocabulary.py --scrape       # Scrape descriptions from phenxtoolkit.org
    python build_phenx_vocabulary.py --scrape --id 10101  # Scrape single protocol
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PHENX_DIR = Path(__file__).parent / "source" / "phenx"
OUTPUT_DIR = Path(__file__).parent / "output"
PROTOCOL_ID_NAME_PATH = PHENX_DIR / "protocol_id_name.xls"
VARIABLE_XREF_PATH = PHENX_DIR / "Variable_cross_reference.xlsx"
DESCRIPTIONS_CACHE_PATH = PHENX_DIR / "protocol_descriptions.json"
OUTPUT_PATH = OUTPUT_DIR / "phenx-concept-vocabulary.json"

PHENX_BASE_URL = "https://www.phenxtoolkit.org/protocols/view"

# Max description length in characters for the classifier prompt.
# Longer descriptions are truncated at the last sentence boundary.
MAX_DESC_CHARS = 250


def slugify(name: str) -> str:
    """Convert a protocol name to a concept_id slug.

    Args:
        name: Human-readable protocol name (e.g., "Blood Pressure").

    Returns:
        Lowercase slug with underscores (e.g., "blood_pressure").
    """
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def load_protocol_names(path: Path) -> dict[int, str]:
    """Load protocol_id -> name mapping from the XLS file.

    Args:
        path: Path to protocol_id_name.xls.

    Returns:
        Dict mapping protocol_id (int) to protocol name (str).
    """
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)
    result = {}
    for i in range(1, ws.nrows):
        row = ws.row_values(i)
        pid = int(row[0])
        name = str(row[1]).strip()
        if name:
            result[pid] = name
    return result


def load_mapped_protocols(path: Path) -> dict[str, dict]:
    """Load protocol stats from Variable_cross_reference.xlsx.

    Args:
        path: Path to Variable_cross_reference.xlsx.

    Returns:
        Dict keyed by protocol name with counts of mapped phv IDs and studies.
    """
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb.active

    protocols: dict[str, dict] = {}
    seen_rows: set[tuple] = set()

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        protocol_name = row[2]
        phv_id = row[5]
        study_id = row[6]

        if not protocol_name or not phv_id:
            continue
        protocol_name = str(protocol_name).strip()
        phv_id = str(phv_id).strip()

        # Deduplicate rows (the XLSX has duplicates)
        row_key = (protocol_name, phv_id)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        if protocol_name not in protocols:
            protocols[protocol_name] = {
                "phv_count": 0,
                "studies": set(),
            }
        protocols[protocol_name]["phv_count"] += 1
        if study_id:
            # Extract base study ID (phs######)
            sid = str(study_id).strip().split(".")[0]
            protocols[protocol_name]["studies"].add(sid)

    wb.close()
    return protocols


def scrape_protocol_description(protocol_id: int) -> dict | None:
    """Fetch description and purpose from phenxtoolkit.org.

    Args:
        protocol_id: PhenX protocol ID (e.g. 10101).

    Returns:
        Dict with 'description' and 'purpose' keys, or None on failure.
    """
    import urllib.request
    import urllib.error

    # The XLS protocol_id encodes version in last 2 digits (e.g. 10101 = protocol 101, v01).
    # The website may have a newer version, so try the XLS version first, then +1.
    base = (protocol_id // 100) * 100
    version = protocol_id % 100
    ids_to_try = [protocol_id]
    # Try next version if XLS version doesn't have content
    if version < 10:
        ids_to_try.append(base + version + 1)

    html = None
    for pid in ids_to_try:
        url = f"{PHENX_BASE_URL}/{pid}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NCPI-Catalog/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            # Check if page has actual protocol content (not just domain listing)
            if "<h5>Description</h5>" in html:
                break
            html = None
        except (urllib.error.URLError, TimeoutError):
            continue

    if not html:
        return None

    # Extract text between common markers.  The PhenX pages have
    # "Description" and "Selection Rationale" / "Purpose" sections.
    result = {}
    for field, patterns in [
        ("description", [
            r"<h\d[^>]*>\s*Description\s*</h\d>\s*(.*?)(?=<h\d|$)",
        ]),
        ("purpose", [
            r"<h\d[^>]*>\s*Purpose\s*</h\d>\s*(.*?)(?=<h\d|$)",
            r"<h\d[^>]*>\s*Selection Rationale\s*</h\d>\s*(.*?)(?=<h\d|$)",
        ]),
    ]:
        for pattern in patterns:
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                import html as html_mod
                text = re.sub(r"<[^>]+>", " ", m.group(1))
                text = html_mod.unescape(text)
                text = re.sub(r"\s+", " ", text).strip()
                # Remove trailing navigation/boilerplate
                text = re.split(r"(?:Back to top|Related protocols|References)", text)[0].strip()
                if len(text) > 20:
                    result[field] = text
                    break

    return result if result else None


def scrape_all(protocol_ids: list[int], cache: dict) -> dict:
    """Scrape descriptions for all protocols, updating cache.

    Args:
        protocol_ids: List of protocol IDs to scrape.
        cache: Existing cache dict to update.

    Returns:
        Updated cache dict.
    """
    to_scrape = [pid for pid in protocol_ids if str(pid) not in cache]
    print(f"Scraping {len(to_scrape)} protocols ({len(protocol_ids) - len(to_scrape)} cached)")

    for i, pid in enumerate(to_scrape):
        print(f"  [{i+1}/{len(to_scrape)}] Protocol {pid}...", end="", flush=True)
        result = scrape_protocol_description(pid)
        if result:
            cache[str(pid)] = result
            print(f" OK ({len(result)} fields)")
        else:
            print(" no content")
        # Polite rate limiting
        if i < len(to_scrape) - 1:
            time.sleep(1.0)

    return cache


def condense_description(name: str, scraped: dict | None) -> str:
    """Build a concise description from scraped PhenX data.

    Prefers the 'purpose' text (why the measurement matters) over the
    'description' (how data is collected). Truncates to MAX_DESC_CHARS
    at a sentence boundary.

    Args:
        name: Protocol name (fallback).
        scraped: Dict with 'description' and/or 'purpose', or None.

    Returns:
        Description string for the vocabulary entry.
    """
    if not scraped:
        return f"PhenX protocol: {name}"

    # Prefer purpose (what it measures / why it matters)
    # Fall back to description (how it's collected)
    text = scraped.get("purpose", "") or scraped.get("description", "")
    if not text:
        return f"PhenX protocol: {name}"

    # Clean up HTML entities and artifacts
    import html as html_mod
    text = html_mod.unescape(text)
    text = text.replace('"', "'").replace("  ", " ").strip()

    if len(text) <= MAX_DESC_CHARS:
        return text

    # Truncate at last sentence boundary within limit.
    # Prefer keeping at least 2 sentences for context.
    truncated = text[:MAX_DESC_CHARS]
    last_period = truncated.rfind(".")
    if last_period > 80:
        return truncated[:last_period + 1]

    return truncated.rsplit(" ", 1)[0] + "..."


def build(args: argparse.Namespace) -> None:
    """Build PhenX concept vocabulary.

    Args:
        args: Parsed command-line arguments.
    """
    if not PROTOCOL_ID_NAME_PATH.exists():
        print(f"Error: {PROTOCOL_ID_NAME_PATH} not found", file=sys.stderr)
        sys.exit(1)
    if not VARIABLE_XREF_PATH.exists():
        print(f"Error: {VARIABLE_XREF_PATH} not found", file=sys.stderr)
        sys.exit(1)

    # Load protocol names
    id_to_name = load_protocol_names(PROTOCOL_ID_NAME_PATH)
    print(f"Loaded {len(id_to_name)} protocol names")

    # Build reverse lookup: name -> protocol_id
    name_to_id: dict[str, int] = {name: pid for pid, name in id_to_name.items()}

    # Load mapped protocols (only those with dbGaP mappings)
    mapped = load_mapped_protocols(VARIABLE_XREF_PATH)
    print(f"Found {len(mapped)} protocols with dbGaP mappings")

    # Load cached descriptions
    cache: dict = {}
    if DESCRIPTIONS_CACHE_PATH.exists():
        with open(DESCRIPTIONS_CACHE_PATH) as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} cached descriptions")
    else:
        print("No cached descriptions (run with --scrape to fetch from phenxtoolkit.org)")

    # Build vocabulary entries
    vocabulary = []
    with_desc = 0
    for name, stats in sorted(mapped.items()):
        if name == "#N/A":
            continue
        concept_id = f"phenx:{slugify(name)}"
        pid = name_to_id.get(name)
        scraped = cache.get(str(pid)) if pid else None
        desc = condense_description(name, scraped)
        if scraped:
            with_desc += 1
        entry = {
            "concept_id": concept_id,
            "name": name,
            "description": desc,
            "dbgap_variable_count": stats["phv_count"],
            "dbgap_study_count": len(stats["studies"]),
            "namespace": "phenx",
        }
        vocabulary.append(entry)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(vocabulary, f, indent=2)

    print(f"Wrote {len(vocabulary)} PhenX concepts to {OUTPUT_PATH}")
    print(f"  With scraped descriptions: {with_desc}")
    print(f"  With fallback descriptions: {len(vocabulary) - with_desc}")
    print(f"  Total mapped phv IDs: {sum(v['dbgap_variable_count'] for v in vocabulary)}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Build PhenX concept vocabulary")
    parser.add_argument(
        "--scrape", action="store_true",
        help="Scrape descriptions from phenxtoolkit.org (caches results)",
    )
    parser.add_argument(
        "--id", type=int,
        help="Scrape a single protocol ID (requires --scrape)",
    )
    args = parser.parse_args()

    if args.scrape:
        id_to_name = load_protocol_names(PROTOCOL_ID_NAME_PATH)
        # Load existing cache
        cache: dict = {}
        if DESCRIPTIONS_CACHE_PATH.exists():
            with open(DESCRIPTIONS_CACHE_PATH) as f:
                cache = json.load(f)

        if args.id:
            protocol_ids = [args.id]
            # Force re-scrape for single ID
            cache.pop(str(args.id), None)
        else:
            protocol_ids = sorted(id_to_name.keys())

        cache = scrape_all(protocol_ids, cache)

        PHENX_DIR.mkdir(parents=True, exist_ok=True)
        with open(DESCRIPTIONS_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"Saved {len(cache)} descriptions to {DESCRIPTIONS_CACHE_PATH}")

    build(args)


if __name__ == "__main__":
    main()
