# PRD: Study-Level Demographics

**Issue:** #186 (extraction), #188 (backend integration)
**Status:** Phase 1 complete, Phase 2 in progress
**Date:** 2026-02-17 (original), 2026-02-20 (updated)

## Problem

The NCPI Dataset Catalog holds ~2,700 dbGaP studies. Researchers selecting
studies for cross-platform analysis need to understand the demographic
composition of each cohort — sex/gender breakdown, race/ethnicity
representation — before requesting access. Today, this information is buried
inside individual `var_report.xml` files and is not surfaced in the catalog UI
or search API.

### What exists today

| Layer                          | Demographic data                                                                                              | Limitation                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **var_report.xml** (raw)       | Full enum counts per variable (e.g., Male=1638, Female=2124) and continuous stats (n, mean, median, min, max) | ~2,700 study dirs, thousands of XML files — not queryable              |
| **LLM concept classification** | Variables mapped to canonical concepts ("Sex", "Age", "Race/Ethnicity") with study counts                     | Knows _which_ studies have demographic variables, but not the _values_ |
| **DuckDB store / search API**  | `measurement` facet lets users find studies with "Age" or "Sex" variables                                     | Returns study lists, not demographic distributions                     |
| **Catalog UI**                 | `participantCount` only                                                                                       | No demographic breakdown shown anywhere                                |

### Gap

There is no pipeline step that extracts the actual value distributions and
surfaces them in search results. A researcher cannot answer "which studies
have >40% Hispanic participants?" or see sex breakdowns when comparing
cohorts.

## Goals

1. **Extract** per-study sex and race/ethnicity distributions from dbGaP
   metadata.
2. **Surface** demographics in the search API so results include population
   breakdowns.
3. **Display** demographics on study detail pages.

### Non-goals (this phase)

- Participant-level data — we only use aggregate counts already published by
  dbGaP.
- Label normalization in the extraction layer — extracted labels are stored
  verbatim from each study's dbGaP submission. The search/API layer normalizes
  via `demographic_mappings.json` and exposes canonical labels while preserving
  the raw extracted values for auditing.
- Age extraction — deferred due to ambiguity ("age at what?"). See Future
  Work.

## Source Data

### Subject_Phenotypes var_report.xml (self-reported)

dbGaP requires studies to submit a standardized **Subject_Phenotypes** table
containing core demographic variables. Each variable carries its value
distribution in `<enum>` elements:

```xml
<variable var_name="SEX" calculated_type="enum_integer">
  <description>Biological SEX</description>
  <total><stats>
    <stat n="29" nulls="0"/>
    <enum code="M" count="19">Male</enum>
    <enum code="F" count="10">Female</enum>
  </stats></total>
</variable>
```

Available for ~1,986 studies. Variables are identified by **name pattern
matching** — `sex`/`gender` for sex, `race`/`ethni` for race/ethnicity
(case-insensitive).

### Computed ancestry from dbGaP CSV (genotype-inferred)

The dbGaP Advanced Search CSV includes an `Ancestry (computed)` column for
studies with genotype data — genetically-inferred ancestry groups computed by
dbGaP. Format: `European (60), African American (30), East Asian (10)`.

Available for ~462 studies. Stored as a **separate field** from self-reported
race/ethnicity since they measure different things.

### What we considered but didn't use

- **LLM concept classification** — The original plan was to use LLM-classified
  concepts to find demographic variables across all study tables. We chose
  Subject_Phenotypes instead because it's dbGaP's standardized table, simpler
  to parse, and doesn't require LLM output. Trade-off: we get fewer studies
  (1,212 with sex vs ~2,400 with LLM concepts) but higher confidence in
  variable selection.
- **TOPMed harmonized variables** — Covers only ~30 studies. Not worth the
  complexity for v1. Could be used as validation data in the future.
- **Age** — ~1,000 studies have an AGE variable in Subject_Phenotypes, but
  "age at what?" is ambiguous (enrollment, diagnosis, sample collection).
  Deferred.

## What's Built (Phase 1) — PR #187

### Extraction script

`catalog-build/classification/extract_demographics.py`

**Inputs:**

- `source/dbgap-variables/{studyId}/*_Subject_Phenotypes.var_report.xml`
- `source/2026-01-27-dbgap-advanced-search.csv` (Ancestry column)

**Output:** `classification/output/demographic-profiles.json`

**How it works:**

1. For each study, finds the `*_Subject_Phenotypes.var_report.xml`
2. Identifies sex and race/ethnicity variables by name pattern
3. Extracts `<enum>` distributions (label, count, code)
4. When multiple variables match, picks the one with highest `n`, then fewest
   nulls
5. Skips consent-group variants (`.c1`, `.c2`)
6. Separately parses computed ancestry from the CSV

### Output schema

```json
{
  "extractedAt": "2026-02-20T18:12:44.167195+00:00",
  "stats": {
    "totalStudies": 2782,
    "studiesWithSex": 1212,
    "studiesWithRaceEthnicity": 1064,
    "studiesWithComputedAncestry": 462,
    "totalWithDemographics": 1734
  },
  "studies": {
    "phs000424": {
      "studyName": "GTEx",
      "sex": {
        "variableName": "SEX",
        "variableId": "phv00253006.v2.p2",
        "datasetId": "pht004314.v3",
        "tableName": "GTEx_Subject_Phenotypes",
        "n": 981,
        "nulls": 0,
        "categories": [
          { "label": "Male", "count": 654, "code": "1" },
          { "label": "Female", "count": 327, "code": "2" }
        ]
      },
      "raceEthnicity": {
        "variableName": "RACE",
        "variableId": "phv00253007.v1.p2",
        "datasetId": "pht004314.v3",
        "tableName": "GTEx_Subject_Phenotypes",
        "n": 981,
        "nulls": 0,
        "categories": [
          { "label": "White", "count": 833, "code": "3" },
          { "label": "Black or African American", "count": 124, "code": "2" }
        ]
      },
      "computedAncestry": {
        "n": 185,
        "categories": [
          { "label": "European", "count": 153 },
          { "label": "African American", "count": 25 },
          { "label": "Hispanic1", "count": 3 }
        ]
      }
    }
  }
}
```

**Key design decisions:**

- Labels are **verbatim from the study's dbGaP submission** — not harmonized.
  One study may report `"FEMALE"`, another `"F"`, another `"Female"`.
- Provenance fields (`variableId`, `datasetId`, `tableName`) are stored in the
  extraction output for auditability but stripped from the API response.
- Computed ancestry uses a fixed vocabulary from dbGaP (European, African
  American, East Asian, Hispanic1, Hispanic2, South Asian, Other Asian or
  Pacific Islander, African, Other).

### Coverage

| Dimension         | Studies | % of catalog |
| ----------------- | ------- | ------------ |
| Sex               | 1,212   | 43%          |
| Race/Ethnicity    | 1,064   | 38%          |
| Computed Ancestry | 462     | 17%          |
| Any demographic   | 1,734   | 62%          |

### Tests

`catalog-build/classification/test_extract_demographics.py` — 66 tests
covering unit tests (pure functions, in-memory XML parsing) and integration
tests (filesystem fixtures with stub XML/CSV).

## Phase 2: Backend Integration (Next)

Load `demographic-profiles.json` into the search pipeline so search results
include demographic distributions.

### Approach

Merge demographic data into each study's `raw_json` blob at DuckDB index
build time, following the same pattern used for all other study fields. Strip
provenance fields and pre-compute `percent` for the API response.

### API response shape

Add a `demographics` field to `StudySummary`:

```json
{
  "dbGapId": "phs000424",
  "demographics": {
    "sex": {
      "n": 981,
      "categories": [
        { "label": "Male", "count": 654, "percent": 66.7 },
        { "label": "Female", "count": 327, "percent": 33.3 }
      ]
    },
    "raceEthnicity": {
      "n": 981,
      "categories": [
        { "label": "White", "count": 833, "percent": 84.9 },
        { "label": "Black or African American", "count": 124, "percent": 12.6 }
      ]
    },
    "computedAncestry": {
      "n": 185,
      "categories": [
        { "label": "European", "count": 153, "percent": 82.7 },
        { "label": "African American", "count": 25, "percent": 13.5 }
      ]
    }
  },
  "title": "GTEx",
  ...
}
```

Studies without demographics: `"demographics": null`.

### Files to modify

- `backend/concept_search/api_models.py` — new models + field on StudySummary
- `backend/concept_search/index.py` — load and merge demographics
- `backend/concept_search/api.py` — extract demographics in study summary
- `backend/tests/test_index.py` — tests for merge and round-trip

## Phase 3: Frontend Display (Future)

Surface demographics on study detail pages:

- Add demographic distribution charts/bars to the study detail side column
- Show sex breakdown, race/ethnicity breakdown, computed ancestry when
  available
- Display in the study browse table as optional columns

This requires changes to:

- `catalog/ncpi-platform-studies.json` (merge demographics at catalog build
  time)
- Site config for study detail pages
- New React components for distribution visualization

## Phase 4: Label Harmonization (Future)

The current extraction stores labels verbatim. The scale of the problem varies
dramatically by dimension:

**Sex — mostly standardized.** 1,212 studies, 71 distinct labels, but 96.6%
are just casing variants of Male/Female. A case-insensitive normalization
handles nearly everything. ~41 studies use alternatives (Boy/Girl, Man/Woman)
and ~27 have misclassified variables (survey questions about sexual interest
that matched the `sex` name pattern).

**Race/Ethnicity — severely fragmented.** 1,064 studies, **682 distinct
labels**, with 71.7% appearing in only one study. The same concept can be
expressed 20+ ways — "Black or African American" alone appears as "African
American", "Black", "BLACK", "black", "Black/African American",
"Black/AA", "African-American", "AfricanAmerican", "African_American",
"African Am", etc. Studies freely mix race and ethnicity categories in the
same variable (22.8% include both "White" and "Hispanic" as options).
Country-specific labels ("Japanese", "Finnish", "Kuwaiti") and truncated
strings ("Ameri", "Hawai") add further variation.

**Computed Ancestry — perfectly standardized.** 9 labels from a fixed dbGaP
vocabulary. No normalization needed.

### The challenge

Race/ethnicity harmonization is a substantial effort. The top 20 labels cover
only 63.2% of occurrences; the top 50 cover 73.9%. A normalization table would
need hundreds of entries to reach high coverage, plus fuzzy matching or LLM
assistance for the long tail. This is one of the core problems the NCPI
Dataset Catalog exists to solve — making inconsistent metadata across
thousands of studies searchable and comparable.

### Available resources

- **TOPMed harmonized variable documentation** in
  `catalog-build/source/harmonization-sources/topmed-harmonized/` provides
  canonical codes for sex (`male`/`female`), race (7 categories), and
  Hispanic/Latino ethnicity.
- These cover ~30 TOPMed studies with exact `phv` IDs and R mapping functions.
- The TOPMed race categories (White, Black, Asian, AI_AN, HI_PI, Multiple,
  Other) provide a reasonable target taxonomy for normalization.

### Approach

1. **Sex:** Case-insensitive normalization to Male/Female/Unknown — handles
   96.6% of studies. Small mapping table for the remaining ~40.
2. **Race/Ethnicity:** Build a mapping table from the ~50 most common labels
   to TOPMed canonical codes (covers ~74%). Use LLM or fuzzy matching for
   the long tail (~490 rare labels). Store both raw and normalized labels.
3. **Computed Ancestry:** No action needed — already standardized.
4. Enable cross-study aggregation ("total female participants across all
   selected studies")

## Phase 5: Demographic Filtering (Future)

Enable demographic-aware search queries:

- "Studies with diverse populations"
- "Pediatric cohorts" (requires age extraction)
- "Studies with >500 female participants"
- "Studies with >40% Hispanic participants"

This could be implemented as:

- Numeric filters on demographic counts/percentages
- A new `demographic` facet in the search pipeline
- NLP agent support for demographic queries

## Phase 6: Age Extraction (Future)

Age is available in Subject_Phenotypes for ~1,000 studies but presents
challenges:

- **Ambiguity:** "age at enrollment", "age at diagnosis", "age at sample
  collection" are different things
- **Format variation:** Some studies use continuous stats (mean, median, range),
  others use age buckets (enum-coded)
- **Multi-visit studies:** Age changes across visits

Possible approach:

- Extract continuous stats (n, mean, median, min, max) from the AGE variable
- For enum-coded age, extract category counts
- Label the dimension explicitly (e.g., "Age at enrollment" vs "Age") based
  on variable description

## Risks & Mitigations

| Risk                                                  | Impact            | Mitigation                                                  |
| ----------------------------------------------------- | ----------------- | ----------------------------------------------------------- |
| Subject_Phenotypes not available for all studies      | 38% without sex   | Could fall back to LLM concept + all-table search in future |
| Name pattern matching produces false positives        | Wrong variable    | Only matches in Subject_Phenotypes (small, standardized)    |
| Verbatim labels inconsistent across studies           | Hard to compare   | Phase 4 harmonization; functional for per-study display now |
| Variable selection picks subset table instead of full | Misleading counts | Highest-n heuristic naturally selects enrollment/baseline   |
| Consent-group variants have different counts          | Double-counting   | `.c1`/`.c2` variants filtered out                           |

## Decisions Log

| Decision                                         | Date       | Rationale                                                           |
| ------------------------------------------------ | ---------- | ------------------------------------------------------------------- |
| Use Subject_Phenotypes instead of LLM+all-tables | 2026-02-20 | Simpler, more reliable, no LLM dependency. Trade: fewer studies.    |
| Store labels verbatim (no harmonization)         | 2026-02-20 | Ship faster. Harmonization is a separate phase.                     |
| Skip age extraction                              | 2026-02-20 | Too many "age at what?" variants to resolve cleanly.                |
| Computed ancestry as separate field              | 2026-02-20 | Genotype-inferred ≠ self-reported. Different data, different field. |
| Pre-compute percent in API response              | 2026-02-20 | Avoids every client doing the same division.                        |
| Strip provenance from API, keep in extraction    | 2026-02-20 | API consumers need labels+counts; provenance is for auditing.       |
