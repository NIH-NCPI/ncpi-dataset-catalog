# NCPI Dataset Catalog: How It Works

This document describes how the catalog is built, from raw data sources through
to the search API. Last verified against code: 2026-02-20.

## Motivation

The NCPI Dataset Catalog exists to help researchers **discover** studies across
NIH cloud platforms. The core challenge is that ~2,700 dbGaP studies contain
~340,000 variables with inconsistent naming, no standard ontology, and metadata
scattered across CSV exports, FTP-hosted XML files, and platform APIs.

Our classification strategy **prioritizes recall over precision**: we'd rather
surface a study that might be relevant than miss one that is. A researcher
searching for "blood pressure" should find every study that measured it, even if
a few false positives slip in. As the project matures, we improve precision —
refining concept names, tightening the hierarchy, and adding UMLS grounding —
without sacrificing coverage.

**Key limitation:** All data in the catalog comes from dbGaP's publicly
available metadata — variable names, descriptions, and per-variable aggregate
statistics. There is no participant-level data, so we can only report
distributions for individual variables independently. We can say "this study has
3,369 female participants" and "1,450 Hispanic participants," but not "how many
Hispanic females" — cross-tabulations between variables require authorized
access to the actual study data.

## Overview

```
dbGaP CSV export ──┐
Platform APIs ─────┤
dbGaP FTP server ──┤──► catalog build ──► catalog JSON ──► DuckDB ──► search API
Semantic Scholar ──┤
var_report.xml ────┤
LLM (Haiku) ───────┘
```

The pipeline has five major stages:

1. **Study discovery** — which studies exist and on which platforms
2. **Metadata enrichment** — titles, descriptions, consent codes, participant
   counts
3. **Publication fetching** — PI-curated papers from dbGaP, resolved via
   Semantic Scholar
4. **Variable classification** — 340K dbGaP variables mapped to ~12K concepts
   via LLM, organized into a searchable hierarchy
5. **Demographic distributions** — per-study sex, race/ethnicity, and computed
   ancestry extracted from dbGaP metadata

---

## 1. Study Discovery

The master list of studies comes from a **dbGaP Advanced Search CSV export**
(~3,264 studies with accession IDs, titles, descriptions, disease focus, study
design, molecular data types, and consent codes). This CSV is refreshed
periodically by downloading a new export from dbGaP.

Each study is then tagged with the **platform(s)** that host it — AnVIL, BDC,
CRDC, KFDRC, or dbGaP-only. Per-platform update scripts query each platform's
API for their current study lists and merge the results into a single
platform-to-study mapping (~3,266 entries, since some studies appear on multiple
platforms).

---

## 2. Metadata Enrichment

For each study, the build process extracts structured fields from the dbGaP CSV:

| Field             | Parsed from                 | Example                                                   |
| ----------------- | --------------------------- | --------------------------------------------------------- |
| Participant count | "Study Content" column      | `"705 subjects"` → `705`                                  |
| Consent codes     | "Study Consent" column      | `"HMB-IRB-NPU --- Health/Medical..."` → `["HMB-IRB-NPU"]` |
| Data types        | "Study Molecular Data Type" | `"SNP Genotypes (Array), WGS"`                            |
| Disease focus     | "Study Disease/Focus"       | `"Neoplasms"`                                             |
| Study design      | "Study Design"              | `"Longitudinal Cohort"`                                   |
| Parent study      | "Parent study"              | `"Parent Name (phs000356.v5.p1)"` → `"phs000356"`         |

The CSV description is often truncated, so the build also **fetches the full
description** from the GapExchange XML on dbGaP's FTP server
(`https://ftp.ncbi.nlm.nih.gov/dbgap/studies/{phsId}/`). It picks the latest
version, downloads the XML, and extracts the `<Description>` element — falling
back to the CSV text if FTP is unavailable.

Additional enrichment includes DUOS data-use URLs, GDC project IDs for CRDC
studies, and decoded consent code descriptions.

The result is a catalog of **~2,944 studies** with full metadata.

---

## 3. Publication Fetching

Each dbGaP study's GapExchange XML contains PI-curated publication references as
`<Pubmed pmid="XXXXX"/>` elements. The publication pipeline:

1. **Fetches PMIDs from the FTP server** for every study in the catalog
2. **Batch-resolves all PMIDs via the Semantic Scholar API** — retrieving title,
   authors, year, journal, DOI, and citation counts
3. **Merges publications into the study catalog** in simplified form (first 3
   authors + "et al.", sorted by citation count)

This step takes ~30 minutes due to FTP and API rate limiting.

---

## 4. Variable Classification

This is the heart of the catalog's search capability. It maps ~340,000 dbGaP
variables into canonical concepts so researchers can find studies by what they
measured, not by arbitrary variable names.

### 4a. Parsing the XML

dbGaP publishes `var_report.xml` files for each study — 14,416 XML files across
2,721 studies. Each file describes a dataset table and its variables: name,
`phv` ID, and description. The parser extracts these fields and deduplicates
across consent groups (`.c1`, `.c2` suffixes), producing ~340,617 unique
variables.

Each var_report.xml also contains value distributions (enum counts, continuous
stats) in `<total><stats>` elements. The demographics pipeline (section 5)
extracts these for sex and race/ethnicity variables.

### 4b. LLM concept classification

Each variable is classified by Claude Haiku into a canonical concept name based
on its **name and description** from the var_report.xml. The LLM also receives
the table name and study name for context.

The input sent to the LLM looks like this (one call per batch of up to 100
variables). Each line under VARIABLES is `variable_name: description` where the
description comes from the `<description>` element in the var_report.xml:

```
Study: phs000209 — Multi-Ethnic Study of Atherosclerosis (MESA) Cohort

TABLE: MESA_Classic_Exam1Main  (245 vars)
DESCRIPTION: MESA Classic Exam 1 Main Dataset
VARIABLES:
  gender1: GENDER                    ← XML description
  race1c: RACE / ETHNICITY          ← XML description
  age1c: AGE AT EXAM 1              ← XML description
  bmi1c: BODY MASS INDEX
  cig1c: CIGARETTES PER DAY
  ...
```

The LLM returns a concept name for each variable (e.g., `gender1` → "Sex",
`race1c` → "Race/Ethnicity", `bmi1c` → "Body Mass Index"). The classification
prompt instructs the LLM to use UMLS-style preferred names in Title Case at an
appropriate level of granularity.

Classification is incremental — results are cached per-study, so re-runs only
process new or changed studies. The first complete run cost ~$250 including test
iterations and debugging.

### 4c. Concept hierarchy

The ~12,187 unique concept names are organized into a two-level hierarchy
(27 top-level categories, ~580 mid-level subcategories):

```
Top-level           Mid-level           Leaf concept (study count)
─────────           ─────────           ──────────────────────────

Demographics
├── Sex/Gender
│   ├── Sex (2,401)
│   ├── Gender Identity (5)
│   └── Sex At Birth (2)
├── Age
│   ├── Age (1,198)
│   ├── Age At Sample Collection (229)
│   ├── Age At Enrollment (78)
│   ├── Age At Diagnosis (107)               ← clinical, not demographic
│   └── ... (~40 more age-at-X variants)
├── Race/Ethnicity
│   ├── Race/Ethnicity (1,192)
│   ├── Ethnicity (258)
│   ├── Race (201)
│   └── Hispanic Ethnicity (42)
├── Education
│   ├── Education (111)
│   └── Education Level (44)
├── Social/Family Status
│   └── Marital Status (66)
└── Employment
    └── Employment Status (40)

Cardiovascular
├── Blood Pressure
│   ├── Systolic Blood Pressure (154)
│   └── Diastolic Blood Pressure (148)
├── Heart Rate
│   └── ...
```

For example, in MESA (phs000209) alone, the leaf concept "Systolic Blood
Pressure" maps to all of these variables — different names, different tables,
same concept:

```
sbp5c    SEATED SYSTOLIC BLOOD PRESSURE (mmHg)       phv00175601.v1
s1bp5    SEATED BP: SYSTOLIC 1ST READING (mmHg)      phv00175587.v1
s2bp5    SEATED BP: SYSTOLIC 2ND READING (mmHg)      phv00175591.v1
s3bp5    SEATED BP: SYSTOLIC 3RD READING (mmHg)      phv00175594.v1
avgsys5  FORM: SYS BLOOD PRESSURE: AVERAGE           phv00175762.v1
rbrach5  RIGHT BRACHIAL BP (mmHg)                    phv00174611.v1
```

This is the core value of the classification: a researcher searching for
"systolic blood pressure" finds MESA regardless of whether the variable is
called `sbp5c`, `s1bp5`, or `rbrach5`.

### 4d. Search index and API

The classified concepts are loaded into a DuckDB in-memory database as a
faceted index. Each study has entries across six facets:

| Facet         | Source                     | Example values                          |
| ------------- | -------------------------- | --------------------------------------- |
| `measurement` | LLM concept classification | "Systolic Blood Pressure", "Sex", "BMI" |
| `platform`    | Platform APIs              | "AnVIL", "BDC", "CRDC", "KFDRC"         |
| `focus`       | dbGaP CSV                  | "Cardiovascular Disease", "Neoplasms"   |
| `dataType`    | dbGaP CSV                  | "WGS", "SNP Genotypes (Array)"          |
| `studyDesign` | dbGaP CSV                  | "Longitudinal Cohort", "Case-Control"   |
| `consentCode` | dbGaP CSV                  | "GRU", "HMB", "DS-CA"                   |

### 4e. Natural language search

The search API accepts natural language queries and translates them into faceted
DuckDB queries using three LLM agents:

1. **Extract** — parses the query into mentions with facet guesses
2. **Resolve** — maps each mention to canonical concept values via index search
   (can rewrite terms, e.g., "blood sugar" → "Fasting Glucose")
3. **Structure** — determines boolean logic (include/exclude flags)

Mentions within a facet are OR-ed; across facets they're AND-ed (unless
excluded).

---

## 5. Demographic Distributions

The demographics pipeline extracts per-study sex and race/ethnicity
distributions from two dbGaP data sources — no LLM involved, just direct
parsing of structured metadata.

### 5a. Subject_Phenotypes (self-reported)

dbGaP requires studies to submit a standardized **Subject_Phenotypes** table
containing core demographic variables. The pipeline:

1. Locates each study's `*_Subject_Phenotypes.var_report.xml` (available for
   ~1,986 studies)
2. Identifies sex and race/ethnicity variables by **name pattern** — matching
   variable names containing `sex`/`gender` or `race`/`ethni`
   (case-insensitive)
3. Extracts `<enum>` distributions from the `<total><stats>` element — the
   category labels and counts that dbGaP pre-computes (e.g.,
   `Male=55, Female=45`)
4. When multiple matching variables exist (e.g., `sex` and `gender`), selects
   the one with the highest `n` (participant count), then fewest nulls

The labels and codes are **verbatim from the study's dbGaP submission** — not
harmonized. One study may report `"FEMALE"`, another `"F"`, another `"Female"`.

### 5b. Computed ancestry (genotype-inferred)

The dbGaP Advanced Search CSV includes an `Ancestry (computed)` column for
studies with genotype data — genetically-inferred ancestry groups computed by
dbGaP. The format is `Label (count), Label (count), ...` using a fixed
vocabulary (European, African American, East Asian, Hispanic1, Hispanic2, South
Asian, Other Asian or Pacific Islander, African, Other).

This is available for **~462 studies** and stored as a separate field from
self-reported race/ethnicity since they measure different things.

### 5c. Output

The pipeline produces `demographic-profiles.json` with top-level metadata and a
`studies` map. Each study entry has up to three optional fields:

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
        "n": 981,
        "categories": [
          { "label": "Male", "count": 654 },
          { "label": "Female", "count": 327 }
        ]
      },
      "raceEthnicity": {
        "variableName": "RACE",
        "n": 981,
        "categories": [
          { "label": "White", "count": 833 },
          { "label": "Black or African American", "count": 124 }
        ]
      },
      "computedAncestry": {
        "n": 185,
        "categories": [
          { "label": "European", "count": 153 },
          { "label": "African American", "count": 25 },
          { "label": "Hispanic1", "count": 3 },
          { "label": "East Asian", "count": 2 },
          { "label": "Hispanic2", "count": 2 }
        ]
      }
    }
  }
}
```

Current coverage: **1,212 studies with sex**, **1,064 with race/ethnicity**,
**462 with computed ancestry** (1,734 total with at least one).
