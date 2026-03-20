# PRD: Longitudinal Study Detection and Tagging

## Problem

The catalog classifies variables into medical concepts but discards temporal information — visit numbers, exam time points, and follow-up durations are stripped during classification (CONCEPT_PROMPT.md rule #4). This means users cannot currently answer:

- "Which studies have **longitudinal** blood pressure data?"
- "Which studies measured BMI over **5+ years** of follow-up?"
- "Is this a cross-sectional snapshot or a repeated-measures cohort?"

Longitudinal data is significantly more valuable for many research questions (causal inference, trajectory modeling, time-series analysis). Making this dimension searchable would be a major discovery feature.

## Goal

Tag each (study, concept) pair with:

- **Is longitudinal**: boolean — does this study measure this concept at multiple time points?
- **Duration category**: approximate span of the longitudinal data (e.g., "1yr", "5yr", "10yr+")
- **Number of time points**: how many distinct measurement occasions exist

Store this as a queryable dimension so users can filter studies by longitudinal availability.

## Current State: What the Data Looks Like

### Longitudinal Studies (clear signal)

**Framingham (phs000007)** — multi-generational, decades of follow-up:

- "Systolic Blood Pressure" appears in **32 separate exam tables**
- Table names: `"Clinic Exam Data: Interview, Physical Exam, ECG, ... Exam 29"`, `"... Exam 30"`, `"... Exam 31"`
- Variable descriptions: `"Femoral Neck BMD, Exam 20"`, `"Femoral Neck BMD, Exam 22"`
- Variable names reference time: `"CT SCAN DATE, NUMBER OF DAYS SINCE EXAM 1"`

**MESA (phs000209)** — 5-exam cohort, two structural patterns:

- **Multi-table pattern**: `"MESA Neighborhood Ancillary Study Exam 1"`, `"...Exam 2"`, through `"...Exam 5"` — same concept in separate per-exam tables
- **Single-table pattern**: Variables named `exam1_m_to_a1`, `exam2_m_to_a1`, `exam3_m_to_a1` — multiple exams collapsed into one wide table with suffixed variable names

### Cross-Sectional Studies (different pattern, same multiplicity)

**ALS GWAS (phs000101)** — same concept appears in multiple tables, but NOT longitudinal:

- Tables: `"NINDS ALS Cases (1st Stage)"`, `"Controls (1st st Stage)"`, `"3rd Stage"`
- Same variables repeat across **case/control partitions**, not time points
- No "Exam N" or "Visit N" language — "Stage" refers to diagnostic staging, not follow-up

### Distinguishing Signals

| Signal                           | Longitudinal                                        | Cross-sectional                                   |
| -------------------------------- | --------------------------------------------------- | ------------------------------------------------- |
| Table names contain              | "Exam N", "Visit N", "Wave N", "Followup", "Year N" | "Cases", "Controls", "Stage N", "Cohort A"        |
| Same concept across tables means | Same measurement at different time points           | Same measurement in different participant subsets |
| Variable descriptions mention    | "at Exam 5", "days since Exam 1", "Year 3"          | "age at diagnosis" (single point)                 |
| Variable name suffixes           | `exam1_*`, `v01_*`, `visit2_*`                      | No temporal suffixes                              |

### Ambiguous Cases

- **Tables with null/missing descriptions** — common in ARIC (phs000280, 398 tables, many undescribed)
- **Mixed studies** — MESA has both longitudinal core exams and cross-sectional ancillary sub-studies
- **Single-table longitudinal** — all exams collapsed into one wide table (only detectable from variable name suffixes)
- **Duration estimation** — table names say "Exam 1" and "Exam 5" but don't tell you how many years apart they are

## Proposed Storage

### New DuckDB table: `study_concept_meta`

One row per (study, concept) pair with longitudinal metadata:

```sql
CREATE TABLE study_concept_meta (
  study_id VARCHAR,
  concept VARCHAR,
  is_longitudinal BOOLEAN,
  num_timepoints INTEGER,      -- number of distinct exam/visit tables
  duration_category VARCHAR,   -- null, '1yr', '5yr', '10yr+'
  detection_method VARCHAR,    -- 'table_name', 'variable_suffix', 'llm', 'manual'
  confidence FLOAT,            -- detection confidence (0.0 - 1.0)
  PRIMARY KEY (study_id, concept)
);
```

This table would be:

- **Derived** from the existing per-study LLM classification JSON (which already has study → table → concept structure)
- **Queryable** as a filter dimension: "show me studies where `is_longitudinal = true AND concept = 'Systolic Blood Pressure' AND duration_category IN ('5yr', '10yr+')`"
- **Joinable** to the existing `variables` and `study_facet_values` tables via `study_id`

### Duration Categories

| Category | Meaning                                                    |
| -------- | ---------------------------------------------------------- |
| `null`   | Not longitudinal or duration unknown                       |
| `<1yr`   | Sub-annual repeated measures (e.g., monthly clinic visits) |
| `1yr`    | ~1 year of follow-up                                       |
| `5yr`    | ~2-5 years                                                 |
| `10yr`   | ~5-10 years                                                |
| `10yr+`  | 10+ years (e.g., Framingham)                               |

### UMLS Mapping

UMLS does not have a clean concept for "longitudinal measurement" as a modifier. The closest terms are:

- **C0023981** — "Longitudinal Studies" (study design, not measurement attribute)
- **C0871881** — "Repeated Measures" (from Consumer Health Vocabulary)

Neither maps well to what we need. The longitudinal dimension is better represented as structured metadata on the study-concept pair rather than as a concept in the hierarchy. This keeps the concept tree clean (concepts describe _what_ is measured, not _how often_).

## Detection Approaches

### Approach 1: Heuristic (table name + variable name patterns)

Regex-based detection on table names and variable names:

```
Table name signals (case-insensitive):
  /exam\s*\d+/i          → "Exam 1", "Exam 5"
  /visit\s*\d+/i         → "Visit 1", "Visit 3"
  /wave\s*\d+/i          → "Wave 1", "Wave 2"
  /follow.?up/i          → "Followup", "Follow-up"
  /year\s*\d+/i          → "Year 1", "Year 5"
  /baseline|endpoint/i   → "Baseline", "Endpoint"

Variable name signals:
  /exam\d+_/i            → "exam1_sbp", "exam2_sbp"
  /v\d{2}_/i             → "v01_sbp", "v02_sbp"
  /visit\d+/i            → "visit1_age", "visit2_age"

Negative signals (cross-sectional indicators):
  /cases|controls/i      → case-control partition
  /stage\s*\d+/i         → diagnostic staging (not temporal)
  /cohort|subset/i       → participant subset
```

**Logic**: For each (study, concept) pair, if the concept appears in 2+ tables whose names match longitudinal patterns, tag as longitudinal. Count distinct matching table numbers as `num_timepoints`.

**Pros**: Fast, no API calls, deterministic, easy to audit
**Cons**: Misses single-table longitudinal (variable suffix pattern), can't estimate duration without study metadata, may false-positive on "Stage" ambiguity

### Approach 2: LLM-assisted detection

Post-hoc pass over table metadata — send the LLM a study's table names + descriptions and ask:

- Is this study longitudinal?
- Which tables represent distinct time points?
- What is the approximate duration?

**Pros**: Handles ambiguous cases, can estimate duration from context, catches single-table longitudinal
**Cons**: Cost (~$5-10 for all studies at Haiku rates), non-deterministic, needs prompt engineering

### Approach 3: Hybrid (recommended)

1. **Heuristic first pass** — regex on table names catches the obvious cases (Framingham, MESA-style multi-exam tables) with high confidence
2. **LLM second pass** — only for studies where the heuristic is ambiguous (concept in 2+ tables but no clear longitudinal/cross-sectional signal)
3. **Duration estimation** — always LLM-assisted, since duration requires understanding study context

This minimizes LLM costs while catching edge cases.

### Approach 4: Defer

Build the UMLS normalization pipeline first. Add longitudinal detection as a follow-up phase that operates on the same per-study JSON input. The `study_concept_meta` table can be populated independently and loaded alongside the existing data.

## Open Questions

1. **Duration estimation source**: Can we get study-level follow-up duration from dbGaP metadata (study description, protocol docs) rather than inferring from table names? This would be more reliable.

2. **Single-table longitudinal**: MESA's `exam1_*, exam2_*` pattern in a single table — the current LLM classification assigns one concept per variable, so `exam1_sbp` and `exam2_sbp` would both get "Systolic Blood Pressure". But they'd appear in the same table, so the heuristic (2+ tables) would miss them. Need variable-name suffix detection or LLM assistance.

3. **Granularity**: Should longitudinal tagging be at the study level ("Framingham is longitudinal") or study-concept level ("Framingham has longitudinal blood pressure but cross-sectional genetic data")? The per-concept level is more useful but more expensive to compute.

4. **Searchability**: How should this surface in the UI? Filter facet ("Longitudinal: Yes/No")? Duration slider? Per-concept badge?

5. **Validation**: What's our ground truth for evaluating detection accuracy? TOPMed studies with known follow-up durations? Manual review of top-50 studies?

## Relationship to UMLS Pipeline

This is a **separate workstream** from the UMLS concept normalization pipeline (see plan in `PRD-variable-classification.md` Step 2). Both operate on the same per-study LLM classification JSON as input, but produce independent outputs:

- **UMLS pipeline** → `umls-concept-hierarchy.json` (concept tree with CUI grounding)
- **Longitudinal detection** → `study_concept_meta` table (temporal metadata per study-concept pair)

They can be built in parallel and composed in the backend at query time.
