# Rule Creation Guide

How to classify dbGaP dataset tables into measures for the NCPI Dataset Catalog.

## 1. What is a Phase 1 Measure?

The classification system uses a three-level hierarchy:

- **Domain** (category): e.g. "Cardiovascular", "Pulmonary"
- **Measure** (procedure): e.g. "electrocardiography", "spirometry"
- **Variable** (leaf): e.g. `PR_INTERVAL`, `FEV1`

A **measure** is a standard way of capturing data on a characteristic of a study subject (adapted from [PhenX](https://www.phenxtoolkit.org/)). It corresponds to one specific instrument, device, assay, or procedure.

### The Single-Procedure Test

A table qualifies for Phase 1 classification when **all** of its variables come from **one** measurement procedure. Ask: "What single instrument or device produced every variable in this table?"

**Qualifies (one procedure):**

| Measure | Instrument/Procedure |
|---|---|
| electrocardiography | One ECG device |
| polysomnography | One overnight sleep recording |
| bone-mineral-density | One DXA scanner |
| spirometry | One spirometer |
| retinal-imaging | One fundus camera |
| proteomics | One Olink assay platform |
| lung-ct-imaging | One CT scanner (lung protocol) |
| accelerometer-wearable-data | One wrist-worn accelerometer |

**Does NOT qualify (multiple procedures):**

| Table type | Why it fails |
|---|---|
| Clinical exam | Multiple tests across one visit |
| Survey / questionnaire battery | Self-report, not a device-based measurement |
| "Biomarkers" | Mixed analytes from different assays (CRP + IL-6 + fibrinogen) |
| Medical history | Multiple conditions, no single instrument |
| Medications | Pharmacy records, not a measurement |
| Demographics | Administrative data |
| Mixed visit tables | Variables from >1 measurement procedure |

## 2. Decision Checklist

For each unclassified table, answer these prompts **in order**. If any prompt produces a SKIP, stop and move to the next table.

### Prompt 1: "What instrument or procedure produced this data?"

Look at the table name, description, and variable names. Can you name **one** instrument, device, assay, or procedure?

- **One instrument** -> proceed to Prompt 2
- **Multiple** or **"it depends"** -> SKIP (defer to Phase 2)
- **No instrument** (survey, admin data) -> SKIP

### Prompt 2: "Do all variables in this table come from that one procedure?"

Inspect the actual variable names (not just the table name or description).

- **All variables match** -> proceed to Prompt 3
- **Mixed variables** from different measurement types -> SKIP

> **Trap: misleading table names.** The table `MESA_AncilMesaEpigenomicCBC` sounds like epigenomics but actually contains CBC hematology labs (hematocrit, hemoglobin, WBC, RBC, platelets). Always verify against variable names.

### Prompt 3: "Does a matching measure already exist?"

Check the [current measures list](#6-reference-current-measures) and existing rule files in `rules/`.

- **Exists** -> reuse the same `measure` slug and `domain`
- **Does not exist** -> create a new measure slug:
  - Use kebab-case: `bone-mineral-density`, not `boneMineralDensity`
  - Name after the **procedure**, not the disease: `diabetic-retinopathy` names the grading procedure, `retinal-imaging` names the photography
  - Keep it specific: `body-composition-ct` not `body-composition` (the latter could match serum biomarker tables too)

### Prompt 4: "Is the regex specific enough?"

The regex must match **only** tables containing data from this measure. Test it mentally against sibling tables in the same study.

- **Prefer anchored patterns** (`^prefix`) over substring matches
- **Watch for sibling tables** with similar names but different content

> **Trap: over-broad regex.** In MESA, `(?i)BodyComp` matches both `BodyCompCT` (CT scan data) and `AbdBodyComposition` (serum biomarkers like CRP, fibrinogen, IL-6). The fix: `(?i)BodyCompCT` anchors to the CT-specific table.

- **Use case-insensitive flag** `(?i)` when table naming conventions vary
- **Match on `description`** when table names are opaque (e.g., FHS `bmd0_*` tables matched via description containing "Bone Mineral Density")

### Prompt 5: "Write the rationale."

Every rule must include a `rationale` field that explains:

1. What the abbreviation or prefix means (e.g., "ECGPWAV = ECG P-wave morphology")
2. What variables confirm this is the right measure
3. Any traps future rule authors should know about

> **Trap: DCCT f114 looks like bone density but isn't.** The form name suggested BMD, but variables are bioelectric impedance and waist circumference — a body composition table, not DXA. The rule was removed after spot-checking.

## 3. What to SKIP (Phase 1 Exclusions)

These table types are **always** deferred to Phase 2:

| Category | Examples | Why |
|---|---|---|
| Surveys & questionnaires | SF-36, CES-D, FFQ, SCL-90-R, quality-of-life | Self-report instruments, not device-based measurements |
| Clinical exam composites | Visit tables combining BP + anthropometry + labs | Multiple measurement procedures in one table |
| Biomarker panels | CRP + IL-6 + fibrinogen in one table | Mixed analytes from different assays |
| Study administration | Subject IDs, consent, pedigree, enrollment | Not measurements |
| Assessment batteries | Neuropsych testing, diabetic neuropathy screening | Multiple sub-tests, not one instrument |
| Medications & treatments | Pharmacy records, drug dosing tables | Not measurements |
| Medical history | Diagnosis codes, ICD-9, condition summaries | Not measurements |
| Demographics | Age, race, SES | Not measurements |
| Outcomes / events | Cardiovascular events, mortality, hospitalizations | Adjudicated endpoints, not instrument data |
| Mixed visit tables | Any table where variables come from >1 procedure | Defer to variable-level classification |

## 4. Workflow: Adding Rules for a New Study

### Step 1: Parse the study's tables

```bash
cd catalog-build/classification
python parse_var_reports.py          # Parses all studies, writes output/parsed-tables.json
```

Or if the cache already exists:

```bash
python classify.py --study phs000NNN --dry-run
```

This shows all unclassified tables with their descriptions and variable counts.

### Step 2: Create the rule file

Create `rules/phs000NNN.json`:

```json
{
  "studyId": "phs000NNN",
  "studyName": "Full Study Name",
  "rules": []
}
```

### Step 3: Triage each unclassified table

For each table in the dry-run output:

1. Read the table name and description
2. Look up its variables in `output/parsed-tables.json` (search for the table name)
3. Run through the [decision checklist](#2-decision-checklist)
4. If it passes all 5 prompts, add a rule entry

### Step 4: Write the rule

Each rule is a JSON object in the `rules` array:

```json
{
  "match": { "tableName": "^PREFIX" },
  "measure": "measure-slug",
  "domain": "Domain Name",
  "rationale": "PREFIX = what it stands for. Variables include X, Y, Z confirming this is [measure]. Note: sibling table FOO contains different data.",
  "description": "'Example table description from dbGaP XML'"
}
```

**Fields:**

| Field | Required | Notes |
|---|---|---|
| `match` | Yes | Object with one key: `tableName` (regex on table name) or `description` (regex on XML description) |
| `measure` | Yes | Kebab-case measure slug (see [reference list](#6-reference-current-measures)) |
| `domain` | Yes | Title-case domain name |
| `rationale` | Yes | Why this rule is correct; abbreviation expansions; traps to know about |
| `description` | No | Example table description(s) from dbGaP XML, for human auditing |

**Rule ordering matters** — the classifier uses first-match-wins. Place more specific patterns before general ones. For example, in CHS:

```json
{ "match": { "tableName": "^SHHS.*PSG" }, "measure": "polysomnography" },
{ "match": { "tableName": "^SHHS.*ecg" }, "measure": "electrocardiography" },
{ "match": { "tableName": "SHHS" },        "measure": "polysomnography" }
```

The specific PSG and ECG patterns come first; the catch-all `SHHS` pattern comes last.

### Step 5: Test the rules

```bash
python classify.py --study phs000NNN --dry-run
```

Verify:
- Every MATCH line maps to the expected measure
- No unexpected tables are being captured
- Unclassified tables are genuinely things that should be skipped

### Step 6: Spot-check variable names

For every matched table, inspect 3-5 variable names in `output/parsed-tables.json` to confirm they actually belong to the assigned measure. This is the step that catches misleading table names.

**Red flags during spot-checking:**
- Variable names from a different measurement domain (e.g., hematology vars in an "epigenomics" table)
- Generic variable names like `RESULT`, `VALUE`, `SCORE` mixed with specific instrument vars
- Variables that are clearly from a different procedure than the one you named

### Step 7: Run the full pipeline

```bash
python classify.py                   # All studies
python coverage_report.py            # Generate coverage statistics
```

## 5. Verification: Spot-Check Protocol

After writing rules for a study, perform this verification:

1. **Run dry-run** and review every MATCH line
2. **For each matched table**, open `output/parsed-tables.json` and search for the table name
3. **Read 5 variable names** — do they all come from the instrument you named?
4. **Check sibling tables** — does the regex accidentally match a table with different content?
5. **Check the rationale** — would another person understand why this table was classified this way?

### Known Traps (from past mistakes)

| Study | Trap | What happened |
|---|---|---|
| MESA | `EpigenomicCBC` table name | Sounds like epigenomics, actually contains CBC hematology labs. **Removed.** |
| MESA | `AbdBodyComposition` vs `BodyCompCT` | Former has serum biomarkers, latter has CT data. Regex narrowed to `BodyCompCT`. |
| DCCT | Form `f114` | Table name suggested bone density, variables are bioelectric impedance. **Removed.** |
| General | Survey instruments | SF-36, SCL-90-R, quality-of-life questionnaires are not device-based measures. **Removed from Phase 1.** |

## 6. Reference: Current Measures

20 measures across 12 domains, as defined in the existing rule files.

| Domain | Measure | Instrument / Procedure |
|---|---|---|
| Anthropometry | `body-composition-ct` | CT scan (abdominal adipose tissue) |
| Cardiovascular | `cardiac-mri` | Cardiac MRI |
| Cardiovascular | `carotid-ultrasound` | B-mode / Doppler ultrasound of carotid arteries |
| Cardiovascular | `electrocardiography` | ECG device |
| Cardiovascular | `flow-mediated-dilation` | Brachial artery ultrasound |
| Cardiovascular | `vascular-ct-imaging` | CT scan (coronary calcium, aortic calcification) |
| Environmental | `air-pollution-exposure` | Air quality monitoring / exposure modeling |
| Hepatology | `liver-ct-imaging` | CT scan (hepatic steatosis) |
| High-Throughput Omics | `gene-expression` | RNA expression microarray |
| High-Throughput Omics | `metabolomics` | Mass spectrometry (Metabolon/Broad) |
| High-Throughput Omics | `proteomics` | Olink proximity extension assay |
| Metabolic | `glycated-hemoglobin` | HbA1c laboratory assay |
| Musculoskeletal | `bone-mineral-density` | DXA scanner |
| Neuroimaging | `brain-mri` | Brain MRI |
| Ophthalmology | `diabetic-retinopathy` | Fundus photography (retinopathy grading) |
| Ophthalmology | `retinal-imaging` | Fundus camera (retinal photography) |
| Physical Activity | `accelerometer-wearable-data` | Wrist-worn accelerometer |
| Pulmonary | `lung-ct-imaging` | CT scan (lung protocol) |
| Pulmonary | `spirometry` | Spirometer |
| Sleep | `polysomnography` | Overnight polysomnography recording |

### Studies with Rules

| Study ID | Study Name | Rule count |
|---|---|---|
| `phs000007` | Framingham Heart Study | 5 |
| `phs000086` | DCCT-EDIC Clinical Trial | 3 |
| `phs000209` | Multi-Ethnic Study of Atherosclerosis (MESA) | 17 |
| `phs000280` | Atherosclerosis Risk in Communities (ARIC) | 9 |
| `phs000287` | Cardiovascular Health Study (CHS) | 6 |

### Adding a New Measure

If no existing measure fits, create a new one:

1. **Slug**: kebab-case, named after the procedure (not the disease)
2. **Domain**: choose from the 12 existing domains, or propose a new one
3. **Verify specificity**: the measure should map to exactly one instrument/device/assay
4. Use the new slug consistently across all studies that have this measure
