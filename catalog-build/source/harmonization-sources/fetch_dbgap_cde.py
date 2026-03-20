"""Fetch CDE (Common Data Element) annotations from dbGaP via NCBI Entrez eUtils.

Downloads all dbGaP variables that have UMLS, LOINC, or PhenX annotations
and saves them as JSON for use as seed data in the UMLS grounding pipeline.

Usage:
    python fetch_dbgap_cde.py                  # Fetch all CDE-annotated variables
    python fetch_dbgap_cde.py --type UMLS      # Fetch only UMLS-annotated
    python fetch_dbgap_cde.py --type LOINC     # Fetch only LOINC-annotated
    python fetch_dbgap_cde.py --type PhenX     # Fetch only PhenX-annotated
    python fetch_dbgap_cde.py --sample 50      # Fetch first 50 for testing
    python fetch_dbgap_cde.py --dry-run        # Show counts only, don't download

Rate limiting: 3 requests/second max (NCBI guideline for unauthenticated access).
With an NCBI API key, up to 10/sec is allowed — set NCBI_API_KEY env var.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DB = "gap"
OUTPUT_DIR = Path(__file__).parent
DELAY_SECONDS = 2.0  # seconds between requests (conservative)

CDE_TYPES = ["UMLS", "LOINC", "PhenX"]

# Max IDs per esummary call (NCBI docs say 200 is safe)
SUMMARY_BATCH_SIZE = 200


def _api_key_param() -> dict[str, str]:
    key = os.environ.get("NCBI_API_KEY", "")
    return {"api_key": key} if key else {}


def _fetch_json(url: str) -> dict:
    """Fetch a URL and return parsed JSON, with retry on transient errors."""
    for attempt in range(1, 6):
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 5:
                wait = 5 * attempt
                print(f"\n  HTTP {e.code}, retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                raise
        except (URLError, OSError) as e:
            if attempt < 5:
                wait = 5 * attempt
                print(
                    f"\n  Connection error ({e}), retrying in {wait}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
            else:
                raise
    return {}


def search_cde_variables(cde_type: str, retmax: int = 0) -> tuple[int, list[str]]:
    """Search for dbGaP variables with a specific CDE annotation type.

    Args:
        cde_type: One of 'UMLS', 'LOINC', 'PhenX'.
        retmax: Max IDs to return. 0 = count only.

    Returns:
        (total_count, list_of_entrez_ids)
    """
    params = {
        "db": DB,
        "term": f"{cde_type}[Common Data Element Resource] AND variable[Discriminator]",
        "retmax": retmax,
        "retmode": "json",
        **_api_key_param(),
    }
    url = f"{EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
    data = _fetch_json(url)
    result = data.get("esearchresult", {})
    count = int(result.get("count", 0))
    ids = result.get("idlist", [])
    return count, ids


def fetch_all_ids(cde_type: str, total: int) -> list[str]:
    """Fetch all Entrez IDs for a CDE type using paginated esearch."""
    all_ids: list[str] = []
    page_size = 10000  # esearch max retmax
    pages = (total + page_size - 1) // page_size

    for page in range(pages):
        retstart = page * page_size
        retmax = min(page_size, total - retstart)
        params = {
            "db": DB,
            "term": f"{cde_type}[Common Data Element Resource] AND variable[Discriminator]",
            "retstart": retstart,
            "retmax": retmax,
            "retmode": "json",
            **_api_key_param(),
        }
        url = f"{EUTILS_BASE}/esearch.fcgi?{urlencode(params)}"
        print(
            f"  Fetching IDs {retstart+1}-{retstart+retmax} of {total}...",
            file=sys.stderr,
        )
        data = _fetch_json(url)
        ids = data.get("esearchresult", {}).get("idlist", [])
        all_ids.extend(ids)
        time.sleep(DELAY_SECONDS)

    return all_ids


def fetch_summaries(ids: list[str]) -> list[dict]:
    """Fetch esummary records for a list of Entrez IDs in batches."""
    records = []
    total = len(ids)
    batches = (total + SUMMARY_BATCH_SIZE - 1) // SUMMARY_BATCH_SIZE

    for i in range(0, total, SUMMARY_BATCH_SIZE):
        batch = ids[i : i + SUMMARY_BATCH_SIZE]
        batch_num = i // SUMMARY_BATCH_SIZE + 1
        params = {
            "db": DB,
            "id": ",".join(batch),
            "retmode": "json",
            **_api_key_param(),
        }
        url = f"{EUTILS_BASE}/esummary.fcgi?{urlencode(params)}"
        print(
            f"\r  Summaries: batch {batch_num}/{batches} "
            f"({len(records)}/{total} records)",
            end="",
            file=sys.stderr,
            flush=True,
        )
        data = _fetch_json(url)
        result = data.get("result", {})
        for uid in batch:
            rec = result.get(uid)
            if rec:
                records.append(rec)
        time.sleep(DELAY_SECONDS)

    print(file=sys.stderr)  # newline after progress
    return records


def extract_variable_record(raw: dict) -> dict | None:
    """Extract the fields we care about from an esummary record."""
    # Only keep variable records
    obj_type = raw.get("d_object_type", "")
    if obj_type and "variable" not in obj_type.lower():
        return None

    # Variable data is nested under d_variable_results
    vr = raw.get("d_variable_results", {})

    cde_list = vr.get("d_variable_common_data_element", [])
    cdes = []
    for cde in cde_list:
        resource = cde.get("d_cde_resource", "")
        term = cde.get("d_cde_term", "")
        if resource and term:
            cdes.append({"resource": resource, "term": term})

    if not cdes:
        return None

    # Parse variable_id — format: "phs000956.v4.p1&phv=252976|phv00252976.v1.p1"
    raw_var_id = (vr.get("d_variable_id") or "").strip()
    phv_id = ""
    study_id = ""
    if "|" in raw_var_id:
        phv_id = raw_var_id.split("|")[-1].split(".")[0]
    if "&" in raw_var_id:
        study_id = raw_var_id.split("&")[0]

    # Parent info has study name
    parents = vr.get("d_variable_parent", [])
    study_name = parents[0].get("d_parent_name", "") if parents else ""

    # Dataset info
    ds = vr.get("d_variable_dataset", {})

    # phenx_info contains CUI + preferred term, e.g. " C0001779 Age"
    phenx_info = (vr.get("d_variable_phenx") or "").strip()

    return {
        "uid": raw.get("uid", ""),
        "phv_id": phv_id,
        "variable_name": (vr.get("d_variable_name") or "").strip(),
        "variable_description": (vr.get("d_variable_description") or "").strip(),
        "study_id": study_id,
        "study_name": study_name,
        "dataset_id": (ds.get("d_variable_dataset_id") or "").strip(),
        "dataset_name": (ds.get("d_variable_dataset_name") or "").strip(),
        "cde_annotations": cdes,
        "has_phenx": (vr.get("d_variable_has_phenx") or "").strip(),
        "phenx_info": phenx_info,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch CDE annotations from dbGaP via NCBI Entrez"
    )
    parser.add_argument(
        "--type",
        choices=CDE_TYPES,
        default=None,
        help="Fetch only this CDE type (default: all)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Fetch only first N variables (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts only, don't download",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: dbgap-cde-{type}.json in script dir)",
    )
    args = parser.parse_args()

    types_to_fetch = [args.type] if args.type else CDE_TYPES

    # Step 1: Get counts
    print("=== dbGaP CDE Variable Counts ===", file=sys.stderr)
    counts: dict[str, int] = {}
    for cde_type in types_to_fetch:
        count, _ = search_cde_variables(cde_type, retmax=0)
        counts[cde_type] = count
        print(f"  {cde_type}: {count:,} variables", file=sys.stderr)
        time.sleep(DELAY_SECONDS)

    if args.dry_run:
        print("\nDry run — exiting.", file=sys.stderr)
        return

    # Step 2: Fetch each type
    for cde_type in types_to_fetch:
        total = counts[cde_type]
        if total == 0:
            continue

        fetch_count = min(args.sample, total) if args.sample else total
        print(
            f"\n=== Fetching {cde_type}: {fetch_count:,} of {total:,} variables ===",
            file=sys.stderr,
        )

        # Get IDs
        if args.sample:
            _, ids = search_cde_variables(cde_type, retmax=fetch_count)
            time.sleep(DELAY_SECONDS)
        else:
            ids = fetch_all_ids(cde_type, total)

        print(f"  Got {len(ids):,} IDs", file=sys.stderr)

        # Get summaries
        raw_records = fetch_summaries(ids)
        print(f"  Got {len(raw_records):,} raw records", file=sys.stderr)

        # Extract and clean
        records = []
        for raw in raw_records:
            rec = extract_variable_record(raw)
            if rec:
                records.append(rec)

        print(f"  Kept {len(records):,} variable records with CDE annotations", file=sys.stderr)

        # Save
        if args.output:
            out_path = Path(args.output)
        else:
            out_path = OUTPUT_DIR / f"dbgap-cde-{cde_type.lower()}.json"

        # Summary stats
        studies = {r["study_id"].split(".")[0] for r in records if r["study_id"]}
        unique_terms = set()
        for r in records:
            for cde in r["cde_annotations"]:
                if cde["resource"] == cde_type:
                    unique_terms.add(cde["term"])

        output = {
            "metadata": {
                "cde_type": cde_type,
                "total_available": total,
                "fetched": len(records),
                "unique_studies": len(studies),
                "unique_terms": len(unique_terms),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "variables": records,
        }

        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)
            f.write("\n")

        print(
            f"  Saved to {out_path}\n"
            f"  {len(records):,} variables, {len(studies)} studies, "
            f"{len(unique_terms)} unique {cde_type} terms",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
