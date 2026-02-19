# PRD: Study-Level Demographics Extraction

**Issue:** TBD
**Status:** Draft
**Date:** 2026-02-17

## Problem

The NCPI Dataset Catalog holds ~2,700 dbGaP studies. Researchers selecting
studies for cross-platform analysis need to understand the demographic
composition of each cohort — age distribution, sex/gender breakdown,
race/ethnicity representation — before requesting access. Today, this
information is buried inside individual `var_report.xml` files and is not
surfaced in the catalog UI or search API.

### What exists today

| Layer                          | Demographic data                                                                                              | Limitation                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **var_report.xml** (raw)       | Full enum counts per variable (e.g., Male=1638, Female=2124) and continuous stats (n, mean, median, min, max) | ~2,700 study dirs, thousands of XML files — not queryable              |
| **LLM concept classification** | Variables mapped to canonical concepts ("Sex", "Age", "Race/Ethnicity") with study counts                     | Knows _which_ studies have demographic variables, but not the _values_ |
| **DuckDB store / search API**  | `measurement` facet lets users find studies with "Age" or "Sex" variables                                     | Returns study lists, not demographic distributions                     |
| **Catalog UI**                 | `participantCount` only                                                                                       | No demographic breakdown shown anywhere                                |

### Gap

There is no pipeline step that extracts the actual value distributions from
var_report.xml and rolls them up into per-study demographic profiles. A
researcher cannot answer "which studies have >40% Hispanic participants?" or
"what's the age range of the MESA cohort?" without manually downloading and
inspecting XML.

## Goals

1. **Extract** demographic value distributions from var_report.xml for every
   study that has classified demographic variables.
2. **Normalize** the extracted values into a common schema (standardized
   category labels, consistent age representations).
3. **Store** per-study demographic profiles in a queryable format.
4. **Surface** demographics in the search API so users can filter and compare
   cohorts by population characteristics.

### Non-goals (for this phase)

- Participant-level data or re-identification risk — we only use aggregate
  counts already published by dbGaP.
- Building UI components — this PRD covers the backend pipeline and API only.

## Source Data

### var_report.xml structure

Each variable in the XML carries its value distribution:

```xml
<!-- Enumerated variable (Sex) -->
<variable var_name="SEX" calculated_type="enum_integer">
  <description>SEX</description>
  <total>
    <subject_profile>
      <sex>
        <male>1638</male>
        <female>2124</female>
      </sex>
    </subject_profile>
    <stats>
      <stat n="3762" nulls="0" />
      <enum code="M" count="2124">Female</enum>
      <enum code="F" count="1638">Male</enum>
    </stats>
  </total>
</variable>

<!-- Enumerated variable (Race) -->
<variable var_name="RACE" calculated_type="enum_integer">
  <description>RACE OR ETHNIC BACKGROUND</description>
  <stats>
    <enum code="1" count="3621">White - not of Hispanic origin</enum>
    <enum code="2" count="119">Black - not of Hispanic origin</enum>
    <enum code="3" count="10">Hispanic</enum>
    <enum code="4" count="5">Asian or Pacific Islander</enum>
    <enum code="5" count="7">Other</enum>
    <stat n="3762" nulls="0" />
  </stats>
</variable>

<!-- Continuous variable (Age) -->
<variable var_name="AGE" calculated_type="continuous_integer">
  <stats>
    <stat n="6429" nulls="0" mean="62.1" stddev="10.2"
          median="62" min="45" max="84" />
  </stats>
</variable>
```

Key observations:

- **Enum variables** have `<enum code="..." count="N">Label</enum>` elements.
- **Continuous variables** have `<stat>` with n, mean, stddev, median, min, max.
- **subject_profile** sometimes provides a pre-computed sex breakdown for the
  entire table (not just the variable), useful as a cross-check.
- Null counts are reported, enabling completeness metrics.

### TOPMed harmonized variable documentation (already available)

The TOPMed DCC has published per-study harmonization definitions for
demographic variables in
`catalog-build/source/harmonization-sources/topmed-harmonized/harmonized-variable-documentation/demographic/`.
These provide a proven normalization framework we can adopt directly.

**Harmonized demographic variables:**

| File                        | Canonical codes                                                  | UMLS CUI                   |
| --------------------------- | ---------------------------------------------------------------- | -------------------------- |
| `annotated_sex_1.json`      | `female`, `male`                                                 | C0017249 (Gender identity) |
| `race_us_1.json`            | `AI_AN`, `Asian`, `Black`, `HI_PI`, `Multiple`, `Other`, `White` | C0034510 (Race)            |
| `hispanic_or_latino_1.json` | `HL`, `notHL`, `both`                                            | C2741637 (Hispanic/Latino) |
| `hispanic_subgroup_1.json`  | (sub-categories of Hispanic/Latino)                              | —                          |

Each JSON file contains:

- **`encoded_values`** — the canonical code-to-label mapping
- **`harmonization_units`** — per-study entries with:
  - `component_study_variables` — the specific `phv` IDs used for that study
  - `harmonization_function` — an R function mapping raw values to canonical codes

**Example** (MESA Classic sex harmonization):

```json
{
  "name": "MESA_Classic",
  "component_study_variables": ["phs000209.v13.pht001116.v10.phv00084446.v2"],
  "harmonization_function": "... mutate(annotated_sex = ifelse(gender1 %in% 1, \"male\", \"female\")) ..."
}
```

This gives us two things for free:

1. **A canonical label schema** for sex, race, and ethnicity — no need to
   invent our own normalization table.
2. **A variable-to-study mapping** with the exact `phv` IDs that TOPMed used
   for each study — we can use these as the "known good" primary variable when
   available, falling back to the LLM-classified variables for studies not in
   the TOPMed harmonization set.

**Coverage:** The harmonization covers ~30 TOPMed studies. The remaining
~2,670 studies will rely on LLM-classified variables + label normalization
against the TOPMed canonical codes.

### TOPMed phenotype tags (concept definitions)

`catalog-build/source/harmonization-sources/topmed-phenotype-tags.csv` defines
the phenotype concepts with UMLS CUIs and detailed inclusion/exclusion
instructions. The two demographic rows:

- **Gender** (C0017249): "Self-reported sex or gender identity" — include all
  self-reported sex/gender variables, exclude clinician-assigned or genetic sex.
- **Race/ancestry/ethnicity** (C1830369): "Self-reported race, ancestry or
  ethnicity" — include all self-reported race/ethnicity, exclude
  genetically-determined ancestry (e.g., PCA-based).
- **Age at enrollment/collection** (C0001779): Defined under "Supporting
  phenotypes" — age at enrollment, blood draw, biosample collection, imaging.

These definitions can guide the LLM concept classification when we re-run it
with UMLS API access (see Open Questions).

### LLM concept classification (already built)

`catalog-build/classification/output/llm-concepts/{studyId}.json` maps each
variable to a canonical concept:

```json
{
  "name": "race1c",
  "id": "phv00084444.v2.p3",
  "description": "RACE / ETHNICITY",
  "concept": "Race/Ethnicity"
}
```

Relevant demographic concepts (from concept-hierarchy.json):

| Category           | Top concepts                                                                                                    | Studies covered |
| ------------------ | --------------------------------------------------------------------------------------------------------------- | --------------- |
| **Sex/Gender**     | Sex (2,401), Gender Identity (5), Sex At Birth (<5)                                                             | ~2,423          |
| **Age**            | Age (1,198), Age At Sample Collection (229), Age At Diagnosis (107), Age At Enrollment (78), Year Of Birth (43) | ~2,395          |
| **Race/Ethnicity** | Race/Ethnicity (1,192), Ethnicity (258), Race (201), Hispanic Ethnicity (42)                                    | ~1,900          |
| **Education**      | Education (221)                                                                                                 | 221             |
| **Employment**     | Employment Status (71)                                                                                          | 71              |

## Proposed Schema

### DemographicProfile (per study)

```python
@dataclass
class DemographicProfile:
    db_gap_id: str

    # Sex/Gender — from the variable with the highest n
    sex: EnumDistribution | None

    # Race/Ethnicity — from the variable with the highest n
    race_ethnicity: EnumDistribution | None

    # Age — from the variable with the highest n
    age: ContinuousDistribution | None

    # Metadata
    source_table: str          # dataset/table the values came from
    total_participants: int    # n from the chosen variable
    extraction_date: str


@dataclass
class EnumDistribution:
    """Counts for a categorical variable."""
    variable_name: str
    variable_id: str           # phv ID for provenance
    n: int
    nulls: int
    categories: list[Category]


@dataclass
class Category:
    label: str                 # Human-readable label from XML
    count: int
    code: str                  # Original enum code


@dataclass
class ContinuousDistribution:
    """Summary stats for a numeric variable."""
    variable_name: str
    variable_id: str
    n: int
    nulls: int
    mean: float | None
    stddev: float | None
    median: float | None
    min: float | None
    max: float | None
    # Optional: age buckets if enum-coded
    categories: list[Category] | None
```

### Variable selection heuristic

Many studies have multiple age, sex, or race variables across different tables
and visits. We need a deterministic rule for picking the "primary" variable:

1. **Filter** to variables whose LLM-classified concept matches the target
   demographic (e.g., concept == "Sex" for sex/gender).
2. **Prefer** variables from the table with the highest total `n` (largest
   participant set — likely the enrollment or baseline table).
3. **Break ties** by preferring the variable with the fewest nulls.
4. **Store provenance** (variable ID, table name) so the choice is auditable.

### Label normalization (TOPMed-aligned)

Use the TOPMed harmonized variable canonical codes as the target schema. Map
raw XML enum labels to these codes:

**Sex** (from `annotated_sex_1.json`):

| Raw labels (examples)                                 | Canonical code | Display label |
| ----------------------------------------------------- | -------------- | ------------- |
| "Male", "M", "MALE", "male", "1" (when gender1)       | `male`         | Male          |
| "Female", "F", "FEMALE", "female", "0" (when gender1) | `female`       | Female        |

**Race** (from `race_us_1.json`):

| Raw labels (examples)                                                                    | Canonical code | Display label                                       |
| ---------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------- |
| "White - not of Hispanic origin", "WHITE, CAUCASIAN", "White"                            | `White`        | White or Caucasian                                  |
| "Black - not of Hispanic origin", "BLACK, AFRICAN-AMERICAN", "Black or African American" | `Black`        | Black or African American                           |
| "Asian", "CHINESE AMERICAN", "Asian or Pacific Islander"                                 | `Asian`        | Asian                                               |
| "Native Hawaiian or Pacific Islander"                                                    | `HI_PI`        | Native Hawaiian or other Pacific Islander           |
| "American Indian", "Alaska Native"                                                       | `AI_AN`        | American Indian, Alaskan Native, or Native American |
| "More than one race"                                                                     | `Multiple`     | More than one race                                  |
| "Other", "Hispanic" (when no race given)                                                 | `Other`        | Other race                                          |

**Hispanic/Latino ethnicity** (from `hispanic_or_latino_1.json`):

| Raw labels (examples)                        | Canonical code | Display label          |
| -------------------------------------------- | -------------- | ---------------------- |
| "Hispanic", "Hispanic or Latino", "HISPANIC" | `HL`           | Hispanic or Latino     |
| "Not Hispanic or Latino", "NOT HISPANIC"     | `notHL`        | Not Hispanic or Latino |

**Strategy — two tiers:**

1. **TOPMed-harmonized studies (~30):** Use the `component_study_variables`
   from the harmonization JSONs to identify the exact `phv` IDs. Apply the
   known canonical mapping directly — these are already validated.
2. **All other studies (~2,670):** Use LLM-classified concept + a lookup table
   mapping the ~30 most common raw labels to TOPMed canonical codes. Log
   unmapped labels for review. Do NOT use an LLM for normalization — it's a
   straightforward lookup.

## Pipeline Design

### Step 1: Parse demographic distributions

Extend or complement `parse_var_reports.py` to extract value distributions for
variables classified as demographic concepts.

**Input:**

- `llm-concepts/{studyId}.json` — identifies which variables are demographic
- `dbgap-variables/{studyId}/*.var_report.xml` — contains the distributions

**Process:**

1. **Build the TOPMed lookup.** Parse `demographic/annotated_sex_1.json`,
   `race_us_1.json`, and `hispanic_or_latino_1.json` to create a map of
   `studyId → {sex_phv, race_phv, ethnicity_phv}` for TOPMed-harmonized
   studies. These are the "known good" variable selections.
2. For each study, load its LLM concept file.
3. Collect variables with concepts in the target set: {Sex, Age,
   Race/Ethnicity, Ethnicity, Race, Hispanic Ethnicity, ...}.
4. **Variable selection:**
   - If the study has a TOPMed harmonization entry, prefer those `phv` IDs.
   - Otherwise, apply the selection heuristic (highest n, fewest nulls).
5. For each selected variable, locate it in the corresponding var_report.xml
   by matching `phv` ID. Extract enum counts or continuous stats.
6. Apply label normalization against TOPMed canonical codes.

**Output:** `catalog-build/classification/output/demographic-profiles.json`

```json
{
  "phs000209": {
    "sex": {
      "variableName": "gender1",
      "variableId": "phv00084446.v2.p3",
      "n": 6429,
      "nulls": 0,
      "categories": [
        { "label": "Female", "count": 3369, "code": "0" },
        { "label": "Male", "count": 3060, "code": "1" }
      ]
    },
    "raceEthnicity": {
      "variableName": "race1c",
      "variableId": "phv00084444.v2.p3",
      "n": 6429,
      "nulls": 0,
      "categories": [
        { "label": "White", "count": 2527, "code": "1" },
        { "label": "Chinese American", "count": 775, "code": "2" },
        { "label": "Black or African American", "count": 1677, "code": "3" },
        { "label": "Hispanic or Latino", "count": 1450, "code": "4" }
      ]
    },
    "age": {
      "variableName": "age1c",
      "variableId": "phv00084442.v2.p3",
      "n": 6429,
      "nulls": 0,
      "mean": 62.1,
      "stddev": 10.2,
      "median": 62.0,
      "min": 45,
      "max": 84,
      "categories": null
    },
    "sourceTable": "pht001116.v10",
    "totalParticipants": 6429,
    "extractionDate": "2026-02-17"
  }
}
```

### Step 2: Index in DuckDB

Add a `study_demographics` table (or embed in the existing `studies` JSON):

```sql
CREATE TABLE study_demographics (
    db_gap_id    VARCHAR PRIMARY KEY,
    sex_json     VARCHAR,     -- JSON array of {label, count}
    race_json    VARCHAR,     -- JSON array of {label, count}
    age_json     VARCHAR,     -- JSON object {n, mean, median, min, max, ...}
    total_n      INTEGER,
    FOREIGN KEY (db_gap_id) REFERENCES studies(db_gap_id)
);
```

### Step 3: Expose via search API

Add a `demographics` field to the study summary response:

```python
class StudyDemographics(BaseModel):
    sex: list[CategoryCount] | None
    race_ethnicity: list[CategoryCount] | None
    age: AgeSummary | None
    total_participants: int | None

class CategoryCount(BaseModel):
    label: str
    count: int
    percent: float  # pre-computed for convenience

class AgeSummary(BaseModel):
    n: int
    mean: float | None
    median: float | None
    min: float | None
    max: float | None
```

New API capabilities:

- **Search results** include demographic summaries for each study.
- **Filter** by demographic criteria (future): e.g., "studies with >1000
  female participants" or "median age > 60".

## Coverage Estimate

Based on concept-hierarchy.json:

| Dimension      | Studies with classified variables | Expected extraction rate                                |
| -------------- | --------------------------------- | ------------------------------------------------------- |
| Sex/Gender     | 2,423 / 2,700 (90%)               | High — enum variables with clear counts                 |
| Age            | 2,395 / 2,700 (89%)               | High for continuous stats; some studies use age buckets |
| Race/Ethnicity | 1,900 / 2,700 (70%)               | Medium-high — more label variation to normalize         |
| All three      | ~1,800 (estimate)                 | Core demographic profile for ~67% of studies            |

## Risks & Mitigations

| Risk                                                                              | Impact                                 | Mitigation                                                             |
| --------------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------- |
| Variable selection picks wrong table (e.g., a subset table instead of enrollment) | Misleading counts                      | Prefer table with highest n; log choices for audit                     |
| Label normalization misses edge cases                                             | Inconsistent categories across studies | Start with top-30 labels; log unmapped; iterate                        |
| Some studies have demographics only in coded form without labels                  | Missing or opaque categories           | Fall back to raw code values; flag for manual review                   |
| Consent-group variants (`.c1`, `.c2`) have different counts                       | Double-counting                        | Use deduplicated variables from existing parser (already handles this) |
| Age variables encoded as enums (age buckets) vs continuous                        | Schema mismatch                        | Support both — `categories` for buckets, stats for continuous          |

## Open Questions

1. **Should we extract education, employment, and income** as secondary
   demographics, or keep the scope to sex/age/race for v1?
2. **How to handle multi-visit studies** (e.g., Framingham with 541 tables)?
   For TOPMed-harmonized studies, the harmonization JSONs already specify which
   table/variable to use. For others, the heuristic picks the table with the
   highest n (typically baseline/enrollment). Is that sufficient?
3. **Should demographic filters be a new facet** in the search API (e.g.,
   `demographic` facet), or extend the existing `measurement` facet with
   value-level filtering?
4. **UMLS API key and concept re-classification.** The LLM concept
   classification currently runs without UMLS grounding. Once we have a UMLS
   API key, we should re-run classification for demographic variables
   specifically, using the TOPMed phenotype tag CUIs (C0017249 for Gender,
   C1830369 for Race/Ethnicity, C0001779 for Age) as anchors. This would
   improve variable selection accuracy for non-TOPMed studies. Should we block
   on this or ship v1 with LLM-only classification and iterate?
5. **TOPMed harmonization coverage.** The harmonization JSONs cover ~30 studies.
   Should we extend the same approach by creating new harmonization entries for
   high-priority studies not in the TOPMed set, or is the LLM-based fallback
   sufficient?

## Implementation Phases

### Phase 1: Extraction pipeline

- Write `extract_demographics.py` in `catalog-build/classification/`
- Parse TOPMed harmonization JSONs to build the "known good" variable map
- For TOPMed studies, use specified `phv` IDs; for others, use LLM concepts +
  selection heuristic
- Extract distributions from var_report.xml, normalize labels to TOPMed codes
- Output `demographic-profiles.json`
- Validate against known studies (MESA, Framingham, AREDS) — cross-check
  TOPMed-tier results against the R harmonization functions

### Phase 2: Backend integration

- Load `demographic-profiles.json` into DuckDB store
- Add `demographics` field to study summary API response
- Update search result serialization

### Phase 3: Filtering (future)

- Enable demographic-aware search queries ("studies with diverse populations",
  "pediatric cohorts", "studies with >500 female participants")
- Potentially add demographic facets to the extract/resolve pipeline

### Phase 4: UMLS-grounded re-classification (future)

- With UMLS API key, re-run demographic variable classification using TOPMed
  phenotype tag CUIs as anchors
- Improve variable selection accuracy for non-TOPMed studies
- Potentially extend harmonization entries to high-priority studies beyond the
  TOPMed ~30
