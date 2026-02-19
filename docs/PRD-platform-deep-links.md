# PRD: Platform Deep Links (Study Detail Page)

The study detail page currently shows a "View in AnVIL" link for AnVIL-hosted studies (see `buildViewInAnVIL` in `viewModelBuilders.ts`). This document covers adding equivalent deep links for the remaining three NCPI platforms.

## Current State

| Platform  | Deep link?                                                        | Status                                                                    |
| --------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **AnVIL** | `https://explore.anvilproject.org/datasets?filter=<encoded_json>` | Implemented — filters by `datasets.registered_identifier` using `dbGapId` |
| **BDC**   | Not yet                                                           | Planned                                                                   |
| **CRDC**  | Not yet                                                           | Planned                                                                   |
| **KFDRC** | Not yet                                                           | Blocked (see below)                                                       |

## BDC (BioData Catalyst) — No per-study deep link

**URL pattern:** `https://gen3.biodatacatalyst.nhlbi.nih.gov/discovery`

- The Gen3 Discovery frontend does not support a `keyword` query parameter — the URL simply opens the discovery page where users can search manually.
- Individual study detail pages (`/discovery/<guid>/`) use GUIDs with version+consent group suffixes (e.g., `phs000179.v6.p2.c1`) that don't match the `studyAccession` stored in our catalog (e.g., `phs000179.v6.p2`), so per-study deep links are not feasible.
- **261 BDC studies** in catalog.

## CRDC (GDC Portal) — Medium

**URL pattern:** `https://portal.gdc.cancer.gov/projects/${gdcProjectId}`

- GDC uses project IDs (e.g., `TARGET-AML`, `CPTAC-3`), not phs IDs, in URLs.
- The GDC API provides a phs→projectId mapping at `https://api.gdc.cancer.gov/projects?fields=project_id,dbgap_accession_number&size=100`. All 47 CRDC studies in the catalog have matching GDC project IDs (100% coverage verified Feb 2026).
- **Implementation:** Fetch the mapping at catalog build time and store a `gdcProjectId` field in the catalog data.
- **47 CRDC studies** in catalog.

## KFDRC (Kids First) — Blocked

**Portal URL:** `https://portal.kidsfirstdrc.org/`

- The Kids First portal requires login for all study pages (uses `ProtectedRoute`).
- Studies are identified by internal `SD_*` codes (e.g., `SD_BHJXBDQK`) in portal routes (`/data-exploration/:studyCode`), not phs IDs.
- The FHIR API (`kf-api-fhir-service.kidsfirstdrc.org`) used to refresh KFDRC source data is **dead** (ECONNREFUSED as of Feb 2026). The source file (`catalog-build/source/kfdrc-studies.json`) does not exist.
- The FHIR response never contained `SD_*` codes — only numeric IDs and phs accessions. So even when the refresh worked, it could not provide the mapping needed for deep links.
- The `kf-api-dataservice.kidsfirstdrc.org` API also appears unreachable.

**Best available options for KFDRC:**

1. Link to `https://portal.kidsfirstdrc.org/public-studies` (no login required, but no per-study deep link)
2. Link to `https://portal.kidsfirstdrc.org/studies` (requires login, no per-study deep link)
3. Obtain `SD_*` → phs mapping from the Kids First team and link to `/data-exploration/<SD_CODE>` (requires login)
4. Monitor `https://data.kidsfirstdrc.org` (newer catalog portal, URL structure unknown)

## Implementation Plan

1. Add `buildViewInBDC()` view builder using the keyword search URL pattern
2. Add GDC project ID fetch to the catalog build pipeline; add `buildViewInCRDC()` view builder
3. Add a generic KFDRC portal link (option 1 or 2 above) until a better path is available
4. Add conditional `ConditionalComponent` entries to `overviewSideColumn.ts` for each new platform, matching the existing AnVIL pattern

## KFDRC Data Refresh — Broken

The KFDRC data refresh pipeline is independently broken and should be tracked separately:

- The FHIR endpoint is offline
- No source JSON file exists
- The 37 KFDRC studies currently in the catalog are stale and cannot be updated
- Possible fix: use the Kids First Arranger GraphQL API (if accessible) or coordinate with the KF team for a data dump
