# PRD: Variable Classification Taxonomy

## Overview

This document defines a classification system for collapsing ~340,000+ dbGaP phenotype variables into ~150-200 searchable measures (following PhenX terminology: a "measure" is a standard way of capturing data on a characteristic of a study subject). The goal is to let researchers find studies by what was measured, without needing to know study-specific variable names.

## Example Queries

These queries assume variable-measure search can be combined with study-level metadata filters (disease focus, assay type, platform, participant count).

### Finding studies by measurement type

- _"Which studies measured **systolic blood pressure**?"_ — should match Framingham's `A53`, `B22`, `FO020`, ARIC's `SBPA21`, and equivalent variables across hundreds of studies, regardless of naming convention
- _"Show me studies with **dietary intake** data"_ — should match any study with a food frequency questionnaire, 24-hour dietary recall, or nutrient analysis, without surfacing individual food items (APPLE, BACON, BEER_LITE...)
- _"Find studies that collected **accelerometer** or **wearable** data"_ — should match Framingham's 11,500-variable accelerometer datasets, not as 11,500 hits but as a single measure: "this study has accelerometer data"
- _"Studies with **bone density** measurements"_ — should match DXA scans, CT-derived bone density, and self-reported osteoporosis across studies

### Cross-study variable discovery

- _"What **lipid** measurements exist across all NIH genomic studies?"_ — should return a measure group (Total cholesterol, LDL, HDL, Triglycerides, Lp(a)) with study counts for each
- _"Compare **kidney function** variables across BDC studies"_ — should show which studies have creatinine, cystatin C, eGFR, and urine albumin-creatinine ratio
- _"Which studies have both **echocardiography** and **brain MRI** data?"_ — measure intersection query across two imaging domains

### Browsing what a study offers

- _"What types of measurements does the Framingham Heart Study have?"_ — should return ~120 measures organized by domain, not 57,000 variable names
- _"Does ARIC have **sleep** data?"_ — yes/no answer with measure detail (sleep apnea status, AHI, polysomnography)

## Problem: Why Raw Variables Are Unsearchable

### Scale

An estimated 500,000+ unique phenotype variables exist across ~3,100 dbGaP studies. The largest study (Framingham Heart Study, phs000007) alone has 57,042 unique variable names across 586 dataset tables.

### Structural factors inflating variable counts

Analysis of Framingham reveals six factors that multiply variable counts far beyond the number of distinct measures collected:

| Factor                            | Example                                                                                               | Impact                           |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Longitudinal repetition**       | Blood pressure measured at 31 exam cycles, each with different variable names (`A53`, `B22`, `FO020`) | Same measurement x N time points |
| **Sensor data granularity**       | Accelerometer: hourly counts x 7 days x multiple metrics = 11,500 variables per dataset               | 1 measure -> 11,500 variables    |
| **Questionnaire line items**      | FFQ: individual food items (APPLE, BACON, YOGURT_FROZEN...) ~700 per version x 6 versions             | 1 measure -> 4,200 variables     |
| **High-throughput omics**         | OLINK proteomics panels, metabolomics mass-spec features, RNA expression probes                       | 1 measure -> 800-3,400 variables |
| **Derived/harmonized versions**   | TOPMed re-derives variables from raw data, creating parallel datasets                                 | 2x variable count                |
| **Per-consent-group duplication** | Each variable repeated per consent group in XML (`.c1`, `.c2` suffixes)                               | 2-3x XML element count           |

### Variable name chaos

The same measure uses completely different names across studies:

| Measure                 | Framingham            | ARIC               | JHS            |
| ----------------------- | --------------------- | ------------------ | -------------- |
| Systolic blood pressure | `A53`, `B22`, `FO020` | `SBPA21`, `SBPA41` | varies by form |
| Subject identifier      | `shareid`             | `ID_C`             | `subjid`       |
| Cohort membership       | `idtype`              | varies             | varies         |

Keyword search on variable names fails. Even description-based search has gaps: CARDIA (phs000285, 328 dataset tables) has only 6 unique dataset descriptions, all generic identifiers like "Subject ID". The meaningful information lives in individual variable descriptions within the XML.

## Proposed Taxonomy

### Design principles

1. **Researcher-centric granularity** — categories should match how researchers think about data: "does this study have blood pressure data?" not "does this study have variable phv00054118?"
2. **Collapse repetition** — all exam cycles, consent groups, and hourly bins for the same measure map to one entry
3. **Preserve meaningful distinctions** — systolic vs diastolic BP are separate measures; individual food items are not
4. **Two-level hierarchy** — domains for browsing, measures for search
5. **Extensible** — new measures can be added without restructuring

### Taxonomy: ~30 domains, ~160 measures

#### Demographics and Enrollment

| Measure                 | Description                                                  | Absorbs                         |
| ----------------------- | ------------------------------------------------------------ | ------------------------------- |
| Age                     | Age at enrollment, exam, or collection                       | Age variables across all visits |
| Sex/Gender              | Self-reported sex or gender identity                         |                                 |
| Race/Ethnicity          | Self-reported race, ancestry, or ethnicity                   |                                 |
| Education               | Highest education level completed                            |                                 |
| Marital status          | Current marital or partnership status                        |                                 |
| Geographic site         | Clinic, recruitment site, or field center                    |                                 |
| Subcohort               | Membership in study subcohorts (e.g., Original vs Offspring) |                                 |
| Clinic visit/exam cycle | Indicator of which visit data was collected at               |                                 |

#### Anthropometry

| Measure                 | Description                               |
| ----------------------- | ----------------------------------------- |
| Height                  | Standing body height                      |
| Weight                  | Body weight                               |
| BMI                     | Body mass index                           |
| Waist circumference     | Waist circumference measurement           |
| Hip circumference       | Hip circumference measurement             |
| Waist-hip ratio         | Ratio of waist to hip circumference       |
| Other body measurements | Arm girth, thigh girth, knee height, etc. |

#### Blood Pressure

| Measure                  | Description                                  |
| ------------------------ | -------------------------------------------- |
| Systolic blood pressure  | Resting arm systolic BP by sphygmomanometer  |
| Diastolic blood pressure | Resting arm diastolic BP by sphygmomanometer |
| Hypertension status      | Indicator of hypertension diagnosis          |
| Ankle-brachial index     | Ratio of ankle to arm systolic BP            |

#### Cardiovascular Disease

| Measure                      | Description                          |
| ---------------------------- | ------------------------------------ |
| Myocardial infarction        | MI event status (prevalent/incident) |
| Heart failure                | Heart failure event status           |
| Coronary artery bypass graft | CABG procedure status                |
| Coronary angioplasty         | PCI/angioplasty procedure status     |
| Peripheral vascular disease  | PVD/PAD status, claudication         |
| Venous thromboembolism       | DVT and pulmonary embolism           |
| Valvular heart disease       | Murmurs, valve abnormalities         |

#### Cardiac Imaging

| Measure                        | Description                                                       |
| ------------------------------ | ----------------------------------------------------------------- |
| Echocardiography               | Cardiac ultrasound (chamber size, ejection fraction, wall motion) |
| Coronary artery calcium (CT)   | CAC score from cardiac CT                                         |
| Carotid intima-media thickness | Carotid ultrasound IMT measurements                               |
| Cardiac MRI                    | Cardiac structure and function by MRI                             |
| Aortic imaging                 | Aortic plaque, calcification, dimensions                          |
| Pericardial/epicardial fat     | Fat deposits around the heart (CT-measured)                       |

#### ECG and Arrhythmia

| Measure                            | Description                         |
| ---------------------------------- | ----------------------------------- |
| Resting heart rate (ECG)           | Heart rate from electrocardiogram   |
| QRS duration                       | Ventricular depolarization duration |
| QT interval                        | Ventricular repolarization interval |
| PR interval                        | Atrial-ventricular conduction time  |
| Atrial fibrillation/flutter        | AF/AFL status (prevalent/incident)  |
| Left ventricular hypertrophy (ECG) | LVH indices from ECG criteria       |
| Pacemaker                          | Pacemaker implant status            |

#### Diabetes and Glucose Metabolism

| Measure                     | Description                                       |
| --------------------------- | ------------------------------------------------- |
| Blood glucose               | Fasting or random blood glucose concentration     |
| Insulin                     | Blood insulin concentration                       |
| HbA1c                       | Glycated hemoglobin                               |
| Diabetes status             | Diabetes diagnosis (type 1, type 2, pre-diabetes) |
| Oral glucose tolerance test | OGTT or FSIGT time-series measurements            |

#### Lipids

| Measure           | Description                          |
| ----------------- | ------------------------------------ |
| Total cholesterol | Total cholesterol in blood           |
| LDL cholesterol   | Low-density lipoprotein cholesterol  |
| HDL cholesterol   | High-density lipoprotein cholesterol |
| Triglycerides     | Triglyceride concentration in blood  |
| Lipoprotein(a)    | Lp(a) concentration                  |

#### Hematology and Hemostasis

| Measure                | Description                                           |
| ---------------------- | ----------------------------------------------------- |
| Hematocrit             | Fraction of blood volume as red blood cells           |
| Hemoglobin             | Hemoglobin concentration                              |
| Platelet count         | Platelet cell count                                   |
| Red blood cell count   | RBC count                                             |
| White blood cell count | WBC count and differential                            |
| Fibrinogen             | Fibrinogen concentration                              |
| Coagulation factors    | Factor VII, Factor VIII, von Willebrand factor, PAI-1 |

#### Inflammation

| Measure                    | Description                |
| -------------------------- | -------------------------- |
| C-reactive protein (CRP)   | CRP concentration in blood |
| Interleukin-6              | IL-6 concentration         |
| Homocysteine               | Homocysteine level         |
| Other inflammatory markers | TNF-alpha, ICAM, etc.      |

#### Kidney Function

| Measure                        | Description                           |
| ------------------------------ | ------------------------------------- |
| Serum creatinine               | Creatinine concentration in blood     |
| Cystatin C                     | Cystatin C concentration              |
| Estimated GFR                  | Calculated glomerular filtration rate |
| Urine albumin-creatinine ratio | UACR from urine sample                |
| Uric acid                      | Serum uric acid level                 |

#### Liver Function

| Measure             | Description                        |
| ------------------- | ---------------------------------- |
| ALT/AST             | Alanine/aspartate aminotransferase |
| Liver fat           | CT or MRI-measured hepatic fat     |
| Other liver markers | GGT, bilirubin, albumin            |

#### Thyroid Function

| Measure                  | Description                    |
| ------------------------ | ------------------------------ |
| TSH                      | Thyroid-stimulating hormone    |
| Thyroid hormones (T3/T4) | Free and total T3/T4           |
| Thyroid disease status   | Hypo/hyperthyroidism diagnosis |

#### Hormones and Endocrine

| Measure                      | Description                             |
| ---------------------------- | --------------------------------------- |
| Estrogen/estradiol           | Estrogen or estradiol levels            |
| Testosterone                 | Testosterone levels                     |
| Cortisol                     | Cortisol levels                         |
| Sex hormone-binding globulin | SHBG concentration                      |
| Other hormones               | Aldosterone, DHEA, growth hormone, etc. |

#### Lung and Respiratory

| Measure              | Description                                     |
| -------------------- | ----------------------------------------------- |
| FEV1                 | Forced expiratory volume in 1 second            |
| FVC                  | Forced vital capacity                           |
| COPD status          | Chronic obstructive pulmonary disease diagnosis |
| Asthma status        | Asthma diagnosis                                |
| Asthma severity      | Severity measures, symptom frequency            |
| Respiratory symptoms | Cough, wheeze, dyspnea questionnaires           |

#### Sleep

| Measure              | Description                                   |
| -------------------- | --------------------------------------------- |
| Sleep apnea status   | Obstructive/central sleep apnea diagnosis     |
| Apnea-hypopnea index | AHI severity measure                          |
| Polysomnography      | Oxygen saturation, sleep stages, arousals     |
| Sleep questionnaire  | Self-reported sleep quality, duration, habits |

#### Stroke and Cerebrovascular

| Measure                   | Description                     |
| ------------------------- | ------------------------------- |
| Ischemic stroke           | Ischemic stroke event status    |
| Hemorrhagic stroke        | Hemorrhagic stroke event status |
| Transient ischemic attack | TIA event status                |
| Other/unspecified stroke  | Stroke of unknown type          |

#### Neurocognitive and Mental Health

| Measure                    | Description                                     |
| -------------------------- | ----------------------------------------------- |
| Cognitive screening        | MMSE, MoCA, clock drawing                       |
| Dementia assessment        | Clinical Dementia Rating, Alzheimer's diagnosis |
| Neuropsychological testing | Trail making, digit span, verbal fluency        |
| Brain MRI (structural)     | Brain volumes, white matter hyperintensities    |
| Brain PET imaging          | Tau PET, amyloid PET                            |
| Depression                 | CES-D, PHQ-9, depressive symptoms               |
| Anxiety                    | Anxiety screening measures                      |

#### Musculoskeletal

| Measure              | Description                                |
| -------------------- | ------------------------------------------ |
| Bone mineral density | DXA scans (hip, spine, whole body)         |
| Osteoporosis         | Osteoporosis diagnosis or fracture history |
| Arthritis            | Rheumatoid, osteoarthritis status          |
| Vertebral assessment | Vertebral fractures from imaging           |

#### Ophthalmology

| Measure              | Description                             |
| -------------------- | --------------------------------------- |
| Visual acuity        | Corrected/uncorrected visual acuity     |
| Retinal examination  | Fundus photography, vessel measurements |
| Glaucoma             | Intraocular pressure, cup-to-disc ratio |
| Cataract             | Lens opacity grading                    |
| Macular degeneration | AMD status and grading                  |

#### Hearing

| Measure          | Description                      |
| ---------------- | -------------------------------- |
| Audiometry       | Pure-tone hearing thresholds     |
| Hearing handicap | Self-reported hearing difficulty |

#### Cancer

| Measure          | Description                   |
| ---------------- | ----------------------------- |
| Cancer events    | Cancer diagnosis, type, date  |
| Cancer screening | Mammography, colonoscopy, PSA |

#### Smoking and Substance Use

| Measure             | Description                                             |
| ------------------- | ------------------------------------------------------- |
| Cigarette smoking   | Smoking status, pack-years, age at initiation/cessation |
| Alcohol consumption | Drinks per week, drinking patterns                      |
| Other substance use | Cigars, chewing tobacco, marijuana                      |

#### Dietary Intake

| Measure                      | Description                      | Absorbs                                     |
| ---------------------------- | -------------------------------- | ------------------------------------------- |
| Food frequency questionnaire | Dietary intake by food category  | All individual food items (APPLE, BACON...) |
| Dietary supplements          | Vitamin, mineral, supplement use |                                             |
| Caffeine intake              | Coffee, tea, cola consumption    |                                             |

#### Physical Activity

| Measure                         | Description                                 | Absorbs                                          |
| ------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| Physical activity questionnaire | Self-reported exercise and activity         |                                                  |
| Accelerometer/wearable data     | Device-measured activity and sedentary time | All hourly/daily bins (11,500 vars -> 1 measure) |
| Exercise capacity               | Treadmill test, VO2 max                     |                                                  |

#### Psychosocial

| Measure                     | Description                         |
| --------------------------- | ----------------------------------- |
| Social support/networks     | Social ties, support questionnaires |
| Job strain/work environment | Occupational stress, demand-control |
| Quality of life             | SF-36, general wellbeing            |

#### Reproductive Health

| Measure                     | Description                           |
| --------------------------- | ------------------------------------- |
| Pregnancy history           | Number of pregnancies, complications  |
| Menopausal status           | Pre/post-menopausal, age at menopause |
| Hormone replacement therapy | HRT use and duration                  |

#### Medications

| Measure                      | Description                                |
| ---------------------------- | ------------------------------------------ |
| Cardiovascular medications   | Antihypertensives, statins, anticoagulants |
| Diabetes medications         | Insulin, metformin, other glucose-lowering |
| General medication inventory | Full medication list surveys               |
| Fasting status               | Fasting indicator for blood draws          |

#### High-Throughput Omics

| Measure         | Description                    | Absorbs                                        |
| --------------- | ------------------------------ | ---------------------------------------------- |
| Proteomics      | OLINK, SomaScan protein panels | Individual proteins (800+ vars -> 1 measure)   |
| Metabolomics    | Mass-spec metabolite profiles  | Individual features (1,000+ vars -> 1 measure) |
| Gene expression | RNA-seq, microarray expression | Individual probes (3,400+ vars -> 1 measure)   |
| DNA methylation | Epigenome-wide methylation     | Individual CpG sites                           |
| Lipidomics      | Lipid species profiling        | Individual lipid species                       |

#### Environmental Exposures

| Measure              | Description                         |
| -------------------- | ----------------------------------- |
| Air quality          | PM2.5, ozone, pollution measures    |
| Neighborhood factors | Area deprivation index, walkability |

#### Study Administration

| Measure                    | Description                              |
| -------------------------- | ---------------------------------------- |
| Subject/sample identifiers | IDs, linkage keys                        |
| Pedigree/family structure  | Parent-child relationships               |
| Consent and access         | Consent codes, data use limitations      |
| Sample collection metadata | DNA draw dates, sample types, processing |

## Compression Ratio

Applying this taxonomy to Framingham (the most complex study):

| Raw count                    | Classified count          | Compression |
| ---------------------------- | ------------------------- | ----------- |
| 57,042 unique variable names | ~120-150 measures present | **~400:1**  |
| 586 dataset tables           | ~30 domains               | **~20:1**   |

The largest compressions come from:

| Variable group                  | Raw variables | Measures                               | Ratio    |
| ------------------------------- | ------------- | -------------------------------------- | -------- |
| Accelerometer hourly data       | ~34,000       | 1 (Accelerometer/wearable data)        | 34,000:1 |
| Gene expression probes          | ~3,400        | 1 (Gene expression)                    | 3,400:1  |
| FFQ food items (all versions)   | ~4,200        | 1 (Food frequency questionnaire)       | 4,200:1  |
| Blood pressure (31 exam cycles) | ~557          | 2 measures (Systolic BP, Diastolic BP) | 280:1    |
| OLINK proteins                  | ~780          | 1 (Proteomics)                         | 780:1    |

## Classification Approach

### Overview

Classification uses a three-step pipeline: LLM classification of every variable to a common medical term, normalization of those terms to UMLS concepts, and human review of the results.

```
Source variables (from dbGaP var_report.xml)
  ↓ Step 1: LLM classification — assign a medical concept to every variable
  ↓ Step 2: UMLS normalization — map free-text concepts to UMLS CUIs
  ↓ Step 3: Human review — audit, merge, and correct
  = per-study JSON files (versioned, cached, incrementally updateable)
```

### Step 1: LLM Variable-Level Classification

Every variable in every dbGaP table is classified by an LLM (Claude Haiku) into a standardized medical concept name. The LLM receives one table at a time — the table name, description, and all variables with their descriptions — and returns a concept for each variable.

**Why per-variable, not per-table:** The original approach classified entire tables into a single measure (e.g. "this is an ECG table"). This works for single-procedure tables but fails for the majority of tables that mix variable types (e.g. blood pressure + demographics + admin fields in one table). Per-variable classification captures the actual content.

**Concept naming:** The LLM is instructed to use standard medical terminology as it would appear in MeSH, LOINC, or UMLS. Concept names are free-text in Title Case (e.g. "Systolic Blood Pressure", "Carotid Intima-Media Thickness", "Study Administration"). The prompt provides granularity guidance — concepts should identify the measurement or test, not the individual parameter or the broad category. See `catalog-build/classification/CONCEPT_PROMPT.md` for the full prompt.

**Granularity strategy: leaf concepts first.** Step 1 targets the most specific (leaf-level) concept that meaningfully describes each variable. Parent concepts and domain groupings are derived _after_ classification — either by walking up the UMLS hierarchy once concepts are mapped to CUIs, or via a separate grouping strategy (TBD). This bottom-up approach preserves maximum information: it is easy to roll up "Systolic Blood Pressure" into "Blood Pressure" or "Cardiovascular", but impossible to recover the distinction if the LLM only assigned "Blood Pressure" in the first place.

**Batching:** Variables are sent in batches of up to 100 per API call (to fit within output token limits). Tables with more variables are split into multiple batches, each receiving the same table-level context. Tables within a study are classified concurrently (10 parallel calls). Studies are processed sequentially.

**Incremental processing:** Results are cached as per-study JSON files in `output/llm-concepts/`. Running without flags skips studies that already have output. Re-run a study by deleting its file and running again.

**Cost:** ~$0.001 per variable via Haiku (~$30 for all 450K variables across 2,870 studies). Dominated by output tokens (the LLM returns each variable name + concept as structured JSON).

**Script:** `catalog-build/classification/llm_concept_classify.py`

#### Output format

Per-study file (`output/llm-concepts/{study_id}.json`):

```json
{
  "studyId": "phs000280",
  "studyName": "ARIC",
  "tables": [
    {
      "tableName": "UBMDBF02",
      "datasetId": "pht004209.v4",
      "description": "...",
      "concepts": ["Carotid Intima-Media Thickness", "Study Administration"],
      "variables": [
        {
          "name": "LBIADA45",
          "description": "Derived avg far wall thickness",
          "concept": "Carotid Intima-Media Thickness"
        },
        {
          "name": "SUBJECT_ID",
          "description": "Subject ID",
          "concept": "Study Administration"
        }
      ]
    }
  ]
}
```

Each table carries both the per-variable concept assignments and a deduplicated `concepts` list (the union of its variables' concepts). Studies and the catalog inherit the union of their tables' concepts.

#### Known limitations of Step 1

- **Granularity inconsistency:** The LLM sometimes lumps (e.g. "Smoking Status" covers age-at-onset, cessation, and current status) and sometimes splits (e.g. "Systolic Blood Pressure" vs "Diastolic Blood Pressure"). Prompt tuning and normalization address this.
- **Concept proliferation:** Initial runs produce ~10,000+ unique concept names, many of which are near-duplicates (e.g. "HDL Cholesterol" vs "High-Density Lipoprotein Cholesterol"). Normalization in Step 2 collapses these.
- **Opaque variable names:** When descriptions are empty or cryptic, the LLM guesses from the variable name. These guesses are sometimes wrong. Human review in Step 3 catches these.

### Step 2: UMLS Normalization

After LLM classification produces free-text concept names, the next step maps them to UMLS Concept Unique Identifiers (CUIs). This serves three purposes:

1. **Synonym collapse** — "HDL Cholesterol", "High-Density Lipoprotein Cholesterol", and "HDL-C" all map to one CUI (C2603387), eliminating near-duplicates automatically.
2. **Cross-reference** — each CUI bridges to SNOMED CT, LOINC, MeSH, and ICD codes, enabling interoperability with other systems (TOPMed harmonization, PhenX protocols, clinical EHR data).
3. **Granularity anchoring** — UMLS's hierarchical structure provides a principled way to choose the right level of specificity. If two concept names map to the same CUI, they are synonyms; if they map to parent-child CUIs, the more specific one is preferred.

**Approach:** Use the UMLS API (requires a UMLS Terminology Services account and API key) to search for each unique concept name, retrieve candidate CUIs, and select the best match. The mapping is stored as a normalization file (`output/concept-normalization-map.json`) and applied to rewrite per-study files with canonical concept names.

**Interim approach (before UMLS API access):** LLM-based synonym grouping (`--normalize` flag) asks the LLM to identify groups of concept names that are synonyms and pick a canonical form. This is a useful first pass but less reliable than UMLS lookup.

**Target:** Collapse ~10,000 raw concept names down to ~500-1,000 canonical concepts, each with a UMLS CUI.

### Step 3: Human Review

After normalization, the concept inventory is reviewed to:

1. **Fix misclassifications** — spot-check variables where the concept seems wrong (e.g. a pacemaker flag classified as "Pacemaker" instead of "Electrocardiography").
2. **Merge remaining synonyms** — UMLS won't catch domain-specific groupings (e.g. should "Ankle-Brachial Index" be separate from "Blood Pressure" or merged?). These are judgment calls.
3. **Set granularity policy** — decide which concepts are too broad or too specific for the browsing use case and adjust the prompt or normalization map accordingly.
4. **Build the domain hierarchy** — assign each canonical concept to a domain (e.g. "Cardiovascular", "Pulmonary") for faceted browsing.

Review results feed back as prompt refinements (Step 1) and normalization rules (Step 2), improving future runs.

### Reproducibility

Classification results are cached as versioned JSON files. The LLM is only invoked for new or re-run studies; existing results are stable. When the prompt or model is updated:

1. Re-run classification on a representative sample
2. Diff against previous output to assess drift
3. If acceptable, re-run on the full corpus
4. Commit the updated output files as a new version

## Variable Modifiers

Rather than multiplying measures for every combination of measurement context, each measure carries optional **modifiers** — orthogonal annotations that describe _how_ or _in whom_ a variable was measured:

| Modifier         | Values                                                             | Example                                             |
| ---------------- | ------------------------------------------------------------------ | --------------------------------------------------- |
| **Longitudinal** | single time-point, repeated measures                               | Systolic BP measured at 31 Framingham exam cycles   |
| **Generation**   | proband, offspring, parents, siblings, descendants, third-gen      | Framingham Original Cohort vs Offspring vs Gen3     |
| **Method**       | self-report, device-measured, lab assay, imaging, derived/computed | Physical activity by questionnaire vs accelerometer |
| **Specimen**     | serum, plasma, urine, whole blood, saliva, tissue                  | Creatinine in serum vs urine                        |
| **Fasting**      | fasting, non-fasting, unspecified                                  | Fasting glucose vs random glucose                   |

### Why modifiers instead of separate measures

Without modifiers, supporting "systolic BP in offspring measured longitudinally" would require a combinatorial explosion of measures (Systolic BP × Original Cohort × Offspring × Gen3 × single × longitudinal = 6+ entries for one measurement). Modifiers keep the measure count at ~160 while still enabling precise queries:

- _"Studies with **longitudinal** blood pressure data"_ — filter on measure = Systolic BP + modifier longitudinal = repeated measures
- _"Accelerometer data in **offspring** cohort"_ — measure = Accelerometer/wearable data + modifier generation = offspring
- _"**Fasting** glucose measurements"_ — measure = Blood glucose + modifier fasting = fasting

Modifiers are populated during classification (Phases 1-4) alongside measure assignment. Dataset-level rules can often infer generation (from dataset name patterns like `ex0_*` = Original, `ex1_*` = Offspring) and longitudinal status (from exam-cycle numbering).

## Ontology Alignment

### Evaluated standards

| Standard    | Top-level categories     | Designed for                 | Covers full dbGaP scope?                               | License  |
| ----------- | ------------------------ | ---------------------------- | ------------------------------------------------------ | -------- |
| SNOMED CT   | 19 meta-categories       | Clinical documentation (EHR) | No (no exposures, omics)                               | Licensed |
| LOINC       | ~280 classes             | Lab/observation workflow     | No (no demographics, exposures)                        | Free     |
| HPO         | 23 organ-system          | Rare disease phenotyping     | No (~40% gap: exposures, diet, activity, omics, admin) | Free     |
| PhenX       | 30 research domains      | Research standardization     | Mostly (no omics, study admin)                         | Free     |
| TOPMed tags | 15 domains / 65 measures | Cross-study harmonization    | Partially (heart/lung/blood/sleep focus)               | Free     |

None of these standards provides a ready-made ~30-domain taxonomy covering the full breadth of dbGaP variables (clinical measurements, behavioral exposures, omics, study administration). Each was designed for a different purpose.

#### PhenX domain alignment (30 domains)

PhenX's 30 research domains are the closest match to our taxonomy. The table below shows each PhenX domain and its mapping to our domains:

| PhenX domain                                     | Our domain(s)                           | Alignment |
| ------------------------------------------------ | --------------------------------------- | --------- |
| Alcohol, Tobacco and Other Substances            | Smoking and Substance Use               | Direct    |
| Anthropometrics                                  | Anthropometry                           | Direct    |
| Bone and Joint                                   | Musculoskeletal                         | Direct    |
| Cancer                                           | Cancer                                  | Direct    |
| Cancer Outcomes and Survivorship                 | Cancer                                  | Merged    |
| Cardiovascular                                   | Cardiovascular Disease, Cardiac Imaging | Split     |
| Demographics                                     | Demographics and Enrollment             | Direct    |
| Diabetes                                         | Diabetes and Glucose Metabolism         | Direct    |
| Environmental Exposures                          | Environmental Exposures                 | Direct    |
| Gastrointestinal                                 | _(not in our taxonomy)_                 | Gap       |
| Genomic Medicine Implementation                  | _(not in our taxonomy)_                 | Gap       |
| Geriatrics                                       | _(cross-cutting, not a domain)_         | N/A       |
| Infectious Diseases and Immunity                 | _(not in our taxonomy)_                 | Gap       |
| Neurology                                        | Neurocognitive and Mental Health        | Direct    |
| Nutrition and Dietary Supplements                | Dietary Intake                          | Direct    |
| Obesity                                          | Anthropometry (BMI measure)             | Merged    |
| Ocular                                           | Ophthalmology                           | Direct    |
| Oral Health                                      | _(not in our taxonomy)_                 | Gap       |
| Pediatric Development                            | _(not in our taxonomy)_                 | Gap       |
| Physical Activity and Physical Fitness           | Physical Activity                       | Direct    |
| Pregnancy                                        | Reproductive Health                     | Direct    |
| Psychiatric                                      | Neurocognitive and Mental Health        | Merged    |
| Psychosocial                                     | Psychosocial                            | Direct    |
| Rare Genetic Conditions                          | _(not in our taxonomy)_                 | Gap       |
| Reproductive Health                              | Reproductive Health                     | Direct    |
| Skin                                             | _(not in our taxonomy)_                 | Gap       |
| Respiratory                                      | Lung and Respiratory                    | Direct    |
| Smoking Cessation, Harm Reduction and Biomarkers | Smoking and Substance Use               | Merged    |
| Social Environments                              | Psychosocial, Environmental Exposures   | Split     |
| Speech, Language and Hearing                     | Hearing                                 | Direct    |

**22 of 30** PhenX domains map directly or merge cleanly into our taxonomy. The 7 PhenX gaps (Gastrointestinal, Genomic Medicine Implementation, Infectious Diseases, Oral Health, Pediatric Development, Rare Genetic Conditions, Skin) represent domains with low prevalence in the large longitudinal cohort studies that dominate dbGaP. These could be added as domains if future studies warrant it.

Our taxonomy adds domains PhenX lacks: **Blood Pressure** (separate from Cardiovascular), **ECG and Arrhythmia**, **Lipids**, **Hematology**, **Inflammation**, **Kidney Function**, **Liver Function**, **Thyroid Function**, **Hormones and Endocrine**, **Sleep**, **Stroke**, **Cardiac Imaging**, **Medications**, **High-Throughput Omics**, and **Study Administration**.

#### HPO cross-reference (23 organ-system categories)

HPO's 23 top-level categories under "Phenotypic abnormality" (HP:0000118) provide a clinical frame that partially overlaps our taxonomy:

| HPO category                                   | Our domain(s)                                                                                                                    | Notes                                   |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Abnormality of the cardiovascular system       | Blood Pressure, CVD, Cardiac Imaging, ECG                                                                                        | Spans 4 of our domains                  |
| Abnormality of blood and blood-forming tissues | Hematology                                                                                                                       |                                         |
| Abnormality of the respiratory system          | Lung and Respiratory                                                                                                             |                                         |
| Abnormality of the nervous system              | Neurocognitive, Stroke                                                                                                           | Spans 2 of our domains                  |
| Abnormality of the eye                         | Ophthalmology                                                                                                                    |                                         |
| Abnormality of the ear                         | Hearing                                                                                                                          |                                         |
| Abnormality of the endocrine system            | Thyroid, Hormones, Diabetes                                                                                                      | Spans 3 of our domains                  |
| Abnormality of the musculoskeletal system      | Musculoskeletal                                                                                                                  |                                         |
| Abnormality of the genitourinary system        | Kidney Function, Reproductive Health                                                                                             |                                         |
| Abnormality of the digestive system            | Liver Function                                                                                                                   | Partial overlap                         |
| Abnormality of the immune system               | Inflammation                                                                                                                     | Partial overlap                         |
| Abnormality of metabolism/homeostasis          | Lipids, Diabetes                                                                                                                 |                                         |
| Growth abnormality                             | Anthropometry                                                                                                                    |                                         |
| Neoplasm                                       | Cancer                                                                                                                           |                                         |
| _(no HPO equivalent)_                          | Demographics, Dietary Intake, Physical Activity, Smoking, Psychosocial, Environmental Exposures, Medications, Omics, Study Admin | ~40% of our taxonomy has no HPO mapping |

HPO is useful as a cross-reference for the clinical/biological domains but cannot serve as the primary taxonomy because it entirely lacks behavioral, exposure, lifestyle, omics, and administrative categories.

#### UMLS Semantic Groups (15 groups / 134 types)

Above individual CUIs, UMLS organizes its concepts into 134 **semantic types** aggregated into 15 **semantic groups**. These provide a coarser roll-up that could serve as a super-domain layer above our 30 domains:

| UMLS Semantic Group         | Relevant to our taxonomy?       | Our domains covered                           |
| --------------------------- | ------------------------------- | --------------------------------------------- |
| Disorders                   | Yes — disease status concepts   | CVD, Diabetes, Stroke, Cancer, Sleep, COPD    |
| Chemicals & Drugs           | Yes — lab analytes, medications | Lipids, Hematology, Inflammation, Medications |
| Procedures                  | Yes — imaging, tests            | Cardiac Imaging, ECG, Ophthalmology           |
| Physiology                  | Yes — measurements              | Blood Pressure, Anthropometry, Lung           |
| Anatomy                     | Indirect — body site context    | _(used as modifier, not a domain)_            |
| Living Beings               | Indirect — species, populations | Demographics (population context)             |
| Measures & Ideas            | Indirect — abstract concepts    | Study Administration                          |
| Activities & Behaviors      | Yes — lifestyle exposures       | Smoking, Physical Activity, Dietary Intake    |
| Phenomena                   | Marginal                        | _(rarely relevant)_                           |
| Objects                     | No                              |                                               |
| Geographic Areas            | Marginal                        | Environmental Exposures                       |
| Organizations               | No                              |                                               |
| Occupations                 | Marginal                        | Psychosocial (job strain)                     |
| Genes & Molecular Sequences | Yes — omics context             | High-Throughput Omics                         |
| Devices                     | Marginal                        | Physical Activity (accelerometers)            |

The 15 UMLS semantic groups are too coarse for our primary browsing UI (e.g., "Disorders" conflates cardiovascular disease, diabetes, cancer, and sleep apnea), but they could serve as a **super-domain grouping** for high-level faceted navigation if needed.

### Adopted approach: custom domains + UMLS CUI identifiers

Following the precedent set by TOPMed's phenotype tagging system:

1. **Keep the custom ~30 domain / ~160 measure taxonomy** defined above. It covers the full scope of dbGaP data in a way no single formal ontology does.
2. **Map each measure to a UMLS CUI** (Concept Unique Identifier). UMLS is the NIH meta-thesaurus that bridges SNOMED CT, LOINC, MeSH, and ICD simultaneously. TOPMed's 65 measures already carry CUI assignments that map directly onto ~60 of our ~160 measures — we extend the pattern to the remaining ~100.
3. **Assign LOINC codes as secondary identifiers** where available. PhenX's 13,653 already-mapped dbGaP variables provide a head start, and the LOINC-SNOMED cooperative ontology bridges both systems.
4. **Use PhenX domain names** where our domains overlap (~22 of 30 PhenX domains) to make the taxonomy familiar to researchers.

### Why UMLS CUIs as the interoperability layer

- **TOPMed already uses them** — 16,671 dbGaP variables tagged with CUI-backed measures across 17 studies; we inherit this work directly.
- **One CUI bridges multiple code systems** — a single CUI like C2039694 (Systolic blood pressure) maps to SNOMED CT 271649006, LOINC 8480-6, and MeSH D001795.
- **PhenX and dbGaP variables can be linked** — PhenX protocols carry LOINC codes, which map to CUIs, creating a bridge from our taxonomy to 13,653 pre-mapped dbGaP variables.
- **Free and maintained by NLM** — no licensing cost, updated quarterly.

### Example CUI mappings for selected measures

| Domain          | Measure                 | UMLS CUI | UMLS Term                            |
| --------------- | ----------------------- | -------- | ------------------------------------ |
| Blood Pressure  | Systolic blood pressure | C2039694 | Systolic blood pressure              |
| Blood Pressure  | Hypertension status     | C3843080 | Hypertension                         |
| Lipids          | HDL cholesterol         | C2603387 | HDL cholesterol measurement          |
| Lipids          | LDL cholesterol         | C2603388 | LDL cholesterol measurement          |
| Hematology      | Hematocrit              | C0518014 | Hematocrit measurement               |
| Kidney Function | Estimated GFR           | C4524116 | Estimated glomerular filtration rate |
| Demographics    | Age                     | C0001779 | Age                                  |
| Inflammation    | C-reactive protein      | C0428528 | C-reactive protein measurement       |
| Sleep           | Apnea-hypopnea index    | C2111846 | Apnea hypopnea index                 |
| Smoking         | Cigarette smoking       | C1519384 | Cigarette smoking                    |

Full CUI assignments for all ~160 measures will be completed during Phase 1 of the classification pipeline.

## Related Documents

- [PRD: Measure Database](./PRD-concept-database.md) — OpenSearch index design, data ingestion pipeline, search capabilities, and confidence tiers. This taxonomy provides the measure vocabulary for that system:
  - Each measure here becomes a record in the `measures` OpenSearch index
  - The domain hierarchy provides faceted browsing structure
  - The classification pipeline (Phases 1-4 above) populates the `mapped_measures` field on variable records
  - TOPMed's 65 existing phenotype tags map directly onto ~60 measures in this taxonomy
- [PRD: Study Publications Discovery](./PRD-study-publications.md) — publication discovery via NIH RePORTER, PMC search, and text mining
- [PRD: Platform Deep Links](./PRD-platform-deep-links.md) — deep links to BDC, CRDC, and KFDRC portals from study detail pages

## Open Questions

1. **Granularity tuning** — Should high-throughput omics be one measure per platform (Proteomics) or broken into sub-panels (OLINK Cardiovascular III, OLINK Organ Damage)?
2. **Medication detail** — Should medications be classified by therapeutic area (CV meds, diabetes meds) or as a single measure?
3. ~~**Temporal annotation** — Should measures carry metadata about whether the study measured them once or longitudinally?~~ **Resolved**: Yes, via the _Longitudinal_ modifier (see Variable Modifiers section above).
4. **Confidence display** — How to present auto-classified measures vs expert-curated ones in the UI?
5. **Coverage target** — What percentage of variables need classification before we ship? (Recommendation: 90% by volume, which Phase 1 + Phase 2 alone may achieve given the heavy-tailed distribution)
6. **CUI coverage** — How many of the ~160 measures have clean 1:1 UMLS CUI mappings? TOPMed's 65 are confirmed; the remainder need manual lookup during Phase 1.

## References

- [TOPMed Phenotype Tagging Details](https://topmed.nhlbi.nih.gov/dcc-phenotype-tagging-details) — 65 expert-curated measures with UMLS CUI mappings
- [TOPMed Phenotype Harmonization (Stilp et al., AJE 2021)](https://academic.oup.com/aje/article/190/10/1977/6228144) — harmonization system and variable tagging methodology
- [PhenX-dbGaP Mapping Paper](https://www.nature.com/articles/s41597-022-01660-4) — 13,653 variables mapped across 521 studies
- [PhenX Toolkit Domains](https://www.phenxtoolkit.org/domains) — 30 research domains for standardized measurement protocols
- [UMLS Semantic Network](https://www.nlm.nih.gov/research/umls/META3_current_semantic_types.html) — 134 semantic types / 15 groups bridging SNOMED CT, LOINC, MeSH, ICD
- [LOINC-SNOMED CT Cooperative Ontology](https://loincsnomed.org/) — joint mapping between observation codes and clinical terms
- [Human Phenotype Ontology](https://hpo.jax.org/) — 23 organ-system phenotype categories (rare disease focus)
- [PRD: Measure Database](./PRD-concept-database.md) — OpenSearch index design, data ingestion, and search architecture
