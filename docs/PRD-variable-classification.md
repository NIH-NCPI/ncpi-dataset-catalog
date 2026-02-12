# PRD: Variable Classification Taxonomy

## Overview

This document defines a classification system for collapsing ~340,000+ dbGaP phenotype variables into ~150-200 searchable concepts. The goal is to let researchers find studies by what was measured, without needing to know study-specific variable names.

## Example Queries

These queries assume variable-concept search can be combined with study-level metadata filters (disease focus, assay type, platform, participant count).

### Finding studies by measurement type

- _"Which studies measured **systolic blood pressure**?"_ — should match Framingham's `A53`, `B22`, `FO020`, ARIC's `SBPA21`, and equivalent variables across hundreds of studies, regardless of naming convention
- _"Show me studies with **dietary intake** data"_ — should match any study with a food frequency questionnaire, 24-hour dietary recall, or nutrient analysis, without surfacing individual food items (APPLE, BACON, BEER_LITE...)
- _"Find studies that collected **accelerometer** or **wearable** data"_ — should match Framingham's 11,500-variable accelerometer datasets, not as 11,500 hits but as a single concept: "this study has accelerometer data"
- _"Studies with **bone density** measurements"_ — should match DXA scans, CT-derived bone density, and self-reported osteoporosis across studies

### Cross-study variable discovery

- _"What **lipid** measurements exist across all NIH genomic studies?"_ — should return a concept group (Total cholesterol, LDL, HDL, Triglycerides, Lp(a)) with study counts for each
- _"Compare **kidney function** variables across BDC studies"_ — should show which studies have creatinine, cystatin C, eGFR, and urine albumin-creatinine ratio
- _"Which studies have both **echocardiography** and **brain MRI** data?"_ — concept intersection query across two imaging domains

### Browsing what a study offers

- _"What types of measurements does the Framingham Heart Study have?"_ — should return ~120 concepts organized by domain, not 57,000 variable names
- _"Does ARIC have **sleep** data?"_ — yes/no answer with concept detail (sleep apnea status, AHI, polysomnography)

## Problem: Why Raw Variables Are Unsearchable

### Scale

An estimated 500,000+ unique phenotype variables exist across ~3,100 dbGaP studies. The largest study (Framingham Heart Study, phs000007) alone has 57,042 unique variable names across 586 dataset tables.

### Structural factors inflating variable counts

Analysis of Framingham reveals six factors that multiply variable counts far beyond the number of distinct concepts measured:

| Factor                            | Example                                                                                               | Impact                           |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Longitudinal repetition**       | Blood pressure measured at 31 exam cycles, each with different variable names (`A53`, `B22`, `FO020`) | Same measurement x N time points |
| **Sensor data granularity**       | Accelerometer: hourly counts x 7 days x multiple metrics = 11,500 variables per dataset               | 1 concept -> 11,500 variables    |
| **Questionnaire line items**      | FFQ: individual food items (APPLE, BACON, YOGURT_FROZEN...) ~700 per version x 6 versions             | 1 concept -> 4,200 variables     |
| **High-throughput omics**         | OLINK proteomics panels, metabolomics mass-spec features, RNA expression probes                       | 1 concept -> 800-3,400 variables |
| **Derived/harmonized versions**   | TOPMed re-derives variables from raw data, creating parallel datasets                                 | 2x variable count                |
| **Per-consent-group duplication** | Each variable repeated per consent group in XML (`.c1`, `.c2` suffixes)                               | 2-3x XML element count           |

### Variable name chaos

The same concept uses completely different names across studies:

| Concept                 | Framingham            | ARIC               | JHS            |
| ----------------------- | --------------------- | ------------------ | -------------- |
| Systolic blood pressure | `A53`, `B22`, `FO020` | `SBPA21`, `SBPA41` | varies by form |
| Subject identifier      | `shareid`             | `ID_C`             | `subjid`       |
| Cohort membership       | `idtype`              | varies             | varies         |

Keyword search on variable names fails. Even description-based search has gaps: CARDIA (phs000285, 328 dataset tables) has only 6 unique dataset descriptions, all generic identifiers like "Subject ID". The meaningful information lives in individual variable descriptions within the XML.

## Proposed Taxonomy

### Design principles

1. **Researcher-centric granularity** — categories should match how researchers think about data: "does this study have blood pressure data?" not "does this study have variable phv00054118?"
2. **Collapse repetition** — all exam cycles, consent groups, and hourly bins for the same concept map to one entry
3. **Preserve meaningful distinctions** — systolic vs diastolic BP are separate concepts; individual food items are not
4. **Two-level hierarchy** — domains for browsing, concepts for search
5. **Extensible** — new concepts can be added without restructuring

### Taxonomy: ~30 domains, ~160 concepts

#### Demographics and Enrollment

| Concept                 | Description                                                  | Absorbs                         |
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

| Concept                 | Description                               |
| ----------------------- | ----------------------------------------- |
| Height                  | Standing body height                      |
| Weight                  | Body weight                               |
| BMI                     | Body mass index                           |
| Waist circumference     | Waist circumference measurement           |
| Hip circumference       | Hip circumference measurement             |
| Waist-hip ratio         | Ratio of waist to hip circumference       |
| Other body measurements | Arm girth, thigh girth, knee height, etc. |

#### Blood Pressure

| Concept                  | Description                                  |
| ------------------------ | -------------------------------------------- |
| Systolic blood pressure  | Resting arm systolic BP by sphygmomanometer  |
| Diastolic blood pressure | Resting arm diastolic BP by sphygmomanometer |
| Hypertension status      | Indicator of hypertension diagnosis          |
| Ankle-brachial index     | Ratio of ankle to arm systolic BP            |

#### Cardiovascular Disease

| Concept                      | Description                          |
| ---------------------------- | ------------------------------------ |
| Myocardial infarction        | MI event status (prevalent/incident) |
| Heart failure                | Heart failure event status           |
| Coronary artery bypass graft | CABG procedure status                |
| Coronary angioplasty         | PCI/angioplasty procedure status     |
| Peripheral vascular disease  | PVD/PAD status, claudication         |
| Venous thromboembolism       | DVT and pulmonary embolism           |
| Valvular heart disease       | Murmurs, valve abnormalities         |

#### Cardiac Imaging

| Concept                        | Description                                                       |
| ------------------------------ | ----------------------------------------------------------------- |
| Echocardiography               | Cardiac ultrasound (chamber size, ejection fraction, wall motion) |
| Coronary artery calcium (CT)   | CAC score from cardiac CT                                         |
| Carotid intima-media thickness | Carotid ultrasound IMT measurements                               |
| Cardiac MRI                    | Cardiac structure and function by MRI                             |
| Aortic imaging                 | Aortic plaque, calcification, dimensions                          |
| Pericardial/epicardial fat     | Fat deposits around the heart (CT-measured)                       |

#### ECG and Arrhythmia

| Concept                            | Description                         |
| ---------------------------------- | ----------------------------------- |
| Resting heart rate (ECG)           | Heart rate from electrocardiogram   |
| QRS duration                       | Ventricular depolarization duration |
| QT interval                        | Ventricular repolarization interval |
| PR interval                        | Atrial-ventricular conduction time  |
| Atrial fibrillation/flutter        | AF/AFL status (prevalent/incident)  |
| Left ventricular hypertrophy (ECG) | LVH indices from ECG criteria       |
| Pacemaker                          | Pacemaker implant status            |

#### Diabetes and Glucose Metabolism

| Concept                     | Description                                       |
| --------------------------- | ------------------------------------------------- |
| Blood glucose               | Fasting or random blood glucose concentration     |
| Insulin                     | Blood insulin concentration                       |
| HbA1c                       | Glycated hemoglobin                               |
| Diabetes status             | Diabetes diagnosis (type 1, type 2, pre-diabetes) |
| Oral glucose tolerance test | OGTT or FSIGT time-series measurements            |

#### Lipids

| Concept           | Description                          |
| ----------------- | ------------------------------------ |
| Total cholesterol | Total cholesterol in blood           |
| LDL cholesterol   | Low-density lipoprotein cholesterol  |
| HDL cholesterol   | High-density lipoprotein cholesterol |
| Triglycerides     | Triglyceride concentration in blood  |
| Lipoprotein(a)    | Lp(a) concentration                  |

#### Hematology and Hemostasis

| Concept                | Description                                           |
| ---------------------- | ----------------------------------------------------- |
| Hematocrit             | Fraction of blood volume as red blood cells           |
| Hemoglobin             | Hemoglobin concentration                              |
| Platelet count         | Platelet cell count                                   |
| Red blood cell count   | RBC count                                             |
| White blood cell count | WBC count and differential                            |
| Fibrinogen             | Fibrinogen concentration                              |
| Coagulation factors    | Factor VII, Factor VIII, von Willebrand factor, PAI-1 |

#### Inflammation

| Concept                    | Description                |
| -------------------------- | -------------------------- |
| C-reactive protein (CRP)   | CRP concentration in blood |
| Interleukin-6              | IL-6 concentration         |
| Homocysteine               | Homocysteine level         |
| Other inflammatory markers | TNF-alpha, ICAM, etc.      |

#### Kidney Function

| Concept                        | Description                           |
| ------------------------------ | ------------------------------------- |
| Serum creatinine               | Creatinine concentration in blood     |
| Cystatin C                     | Cystatin C concentration              |
| Estimated GFR                  | Calculated glomerular filtration rate |
| Urine albumin-creatinine ratio | UACR from urine sample                |
| Uric acid                      | Serum uric acid level                 |

#### Liver Function

| Concept             | Description                        |
| ------------------- | ---------------------------------- |
| ALT/AST             | Alanine/aspartate aminotransferase |
| Liver fat           | CT or MRI-measured hepatic fat     |
| Other liver markers | GGT, bilirubin, albumin            |

#### Thyroid Function

| Concept                  | Description                    |
| ------------------------ | ------------------------------ |
| TSH                      | Thyroid-stimulating hormone    |
| Thyroid hormones (T3/T4) | Free and total T3/T4           |
| Thyroid disease status   | Hypo/hyperthyroidism diagnosis |

#### Hormones and Endocrine

| Concept                      | Description                             |
| ---------------------------- | --------------------------------------- |
| Estrogen/estradiol           | Estrogen or estradiol levels            |
| Testosterone                 | Testosterone levels                     |
| Cortisol                     | Cortisol levels                         |
| Sex hormone-binding globulin | SHBG concentration                      |
| Other hormones               | Aldosterone, DHEA, growth hormone, etc. |

#### Lung and Respiratory

| Concept              | Description                                     |
| -------------------- | ----------------------------------------------- |
| FEV1                 | Forced expiratory volume in 1 second            |
| FVC                  | Forced vital capacity                           |
| COPD status          | Chronic obstructive pulmonary disease diagnosis |
| Asthma status        | Asthma diagnosis                                |
| Asthma severity      | Severity measures, symptom frequency            |
| Respiratory symptoms | Cough, wheeze, dyspnea questionnaires           |

#### Sleep

| Concept              | Description                                   |
| -------------------- | --------------------------------------------- |
| Sleep apnea status   | Obstructive/central sleep apnea diagnosis     |
| Apnea-hypopnea index | AHI severity measure                          |
| Polysomnography      | Oxygen saturation, sleep stages, arousals     |
| Sleep questionnaire  | Self-reported sleep quality, duration, habits |

#### Stroke and Cerebrovascular

| Concept                   | Description                     |
| ------------------------- | ------------------------------- |
| Ischemic stroke           | Ischemic stroke event status    |
| Hemorrhagic stroke        | Hemorrhagic stroke event status |
| Transient ischemic attack | TIA event status                |
| Other/unspecified stroke  | Stroke of unknown type          |

#### Neurocognitive and Mental Health

| Concept                    | Description                                     |
| -------------------------- | ----------------------------------------------- |
| Cognitive screening        | MMSE, MoCA, clock drawing                       |
| Dementia assessment        | Clinical Dementia Rating, Alzheimer's diagnosis |
| Neuropsychological testing | Trail making, digit span, verbal fluency        |
| Brain MRI (structural)     | Brain volumes, white matter hyperintensities    |
| Brain PET imaging          | Tau PET, amyloid PET                            |
| Depression                 | CES-D, PHQ-9, depressive symptoms               |
| Anxiety                    | Anxiety screening measures                      |

#### Musculoskeletal

| Concept              | Description                                |
| -------------------- | ------------------------------------------ |
| Bone mineral density | DXA scans (hip, spine, whole body)         |
| Osteoporosis         | Osteoporosis diagnosis or fracture history |
| Arthritis            | Rheumatoid, osteoarthritis status          |
| Vertebral assessment | Vertebral fractures from imaging           |

#### Ophthalmology

| Concept              | Description                             |
| -------------------- | --------------------------------------- |
| Visual acuity        | Corrected/uncorrected visual acuity     |
| Retinal examination  | Fundus photography, vessel measurements |
| Glaucoma             | Intraocular pressure, cup-to-disc ratio |
| Cataract             | Lens opacity grading                    |
| Macular degeneration | AMD status and grading                  |

#### Hearing

| Concept          | Description                      |
| ---------------- | -------------------------------- |
| Audiometry       | Pure-tone hearing thresholds     |
| Hearing handicap | Self-reported hearing difficulty |

#### Cancer

| Concept          | Description                   |
| ---------------- | ----------------------------- |
| Cancer events    | Cancer diagnosis, type, date  |
| Cancer screening | Mammography, colonoscopy, PSA |

#### Smoking and Substance Use

| Concept             | Description                                             |
| ------------------- | ------------------------------------------------------- |
| Cigarette smoking   | Smoking status, pack-years, age at initiation/cessation |
| Alcohol consumption | Drinks per week, drinking patterns                      |
| Other substance use | Cigars, chewing tobacco, marijuana                      |

#### Dietary Intake

| Concept                      | Description                      | Absorbs                                     |
| ---------------------------- | -------------------------------- | ------------------------------------------- |
| Food frequency questionnaire | Dietary intake by food category  | All individual food items (APPLE, BACON...) |
| Dietary supplements          | Vitamin, mineral, supplement use |                                             |
| Caffeine intake              | Coffee, tea, cola consumption    |                                             |

#### Physical Activity

| Concept                         | Description                                 | Absorbs                                          |
| ------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| Physical activity questionnaire | Self-reported exercise and activity         |                                                  |
| Accelerometer/wearable data     | Device-measured activity and sedentary time | All hourly/daily bins (11,500 vars -> 1 concept) |
| Exercise capacity               | Treadmill test, VO2 max                     |                                                  |

#### Psychosocial

| Concept                     | Description                         |
| --------------------------- | ----------------------------------- |
| Social support/networks     | Social ties, support questionnaires |
| Job strain/work environment | Occupational stress, demand-control |
| Quality of life             | SF-36, general wellbeing            |

#### Reproductive Health

| Concept                     | Description                           |
| --------------------------- | ------------------------------------- |
| Pregnancy history           | Number of pregnancies, complications  |
| Menopausal status           | Pre/post-menopausal, age at menopause |
| Hormone replacement therapy | HRT use and duration                  |

#### Medications

| Concept                      | Description                                |
| ---------------------------- | ------------------------------------------ |
| Cardiovascular medications   | Antihypertensives, statins, anticoagulants |
| Diabetes medications         | Insulin, metformin, other glucose-lowering |
| General medication inventory | Full medication list surveys               |
| Fasting status               | Fasting indicator for blood draws          |

#### High-Throughput Omics

| Concept         | Description                    | Absorbs                                        |
| --------------- | ------------------------------ | ---------------------------------------------- |
| Proteomics      | OLINK, SomaScan protein panels | Individual proteins (800+ vars -> 1 concept)   |
| Metabolomics    | Mass-spec metabolite profiles  | Individual features (1,000+ vars -> 1 concept) |
| Gene expression | RNA-seq, microarray expression | Individual probes (3,400+ vars -> 1 concept)   |
| DNA methylation | Epigenome-wide methylation     | Individual CpG sites                           |
| Lipidomics      | Lipid species profiling        | Individual lipid species                       |

#### Environmental Exposures

| Concept              | Description                         |
| -------------------- | ----------------------------------- |
| Air quality          | PM2.5, ozone, pollution measures    |
| Neighborhood factors | Area deprivation index, walkability |

#### Study Administration

| Concept                    | Description                              |
| -------------------------- | ---------------------------------------- |
| Subject/sample identifiers | IDs, linkage keys                        |
| Pedigree/family structure  | Parent-child relationships               |
| Consent and access         | Consent codes, data use limitations      |
| Sample collection metadata | DNA draw dates, sample types, processing |

## Compression Ratio

Applying this taxonomy to Framingham (the most complex study):

| Raw count                    | Classified count          | Compression |
| ---------------------------- | ------------------------- | ----------- |
| 57,042 unique variable names | ~120-150 concepts present | **~400:1**  |
| 586 dataset tables           | ~30 domains               | **~20:1**   |

The largest compressions come from:

| Variable group                  | Raw variables | Concepts                         | Ratio    |
| ------------------------------- | ------------- | -------------------------------- | -------- |
| Accelerometer hourly data       | ~34,000       | 1 (Accelerometer/wearable data)  | 34,000:1 |
| Gene expression probes          | ~3,400        | 1 (Gene expression)              | 3,400:1  |
| FFQ food items (all versions)   | ~4,200        | 1 (Food frequency questionnaire) | 4,200:1  |
| Blood pressure (31 exam cycles) | ~557          | 2 (Systolic BP, Diastolic BP)    | 280:1    |
| OLINK proteins                  | ~780          | 1 (Proteomics)                   | 780:1    |

## Classification Approach

### Phase 1: Dataset-level rules

Many dataset tables can be classified entirely from their table name or description:

- `t_physactf_*` -> Physical Activity: Accelerometer/wearable data
- `vr_ffreq_*` -> Dietary Intake: Food frequency questionnaire
- `l_rnapilot_*` -> High-Throughput Omics: Gene expression
- `fib0_21s` ("Fibrinogen, Original Cohort Exams 20, 21") -> Hematology: Fibrinogen

This alone could classify ~40-60% of variables by volume (because the high-count datasets are the easiest to identify).

### Phase 2: Keyword rules on variable descriptions

Keyword matching on variable descriptions covers another layer:

| Keyword pattern                            | Variables matched (Framingham) | Concept        |
| ------------------------------------------ | ------------------------------ | -------------- |
| BLOOD PRESSURE, SYSTOLIC, DIASTOLIC        | 557                            | Blood Pressure |
| CHOLESTEROL, LDL, HDL, TRIGLYCERIDE, LIPID | 604                            | Lipids         |
| SMOKING, CIGARETTE                         | 670                            | Smoking        |
| DEPRESSION, CES-D, DEPRESSED               | 559                            | Depression     |
| SLEEP, APNEA, AHI                          | 1,472                          | Sleep          |

Keyword rules could classify an additional ~20-30% of variables.

### Phase 3: Embedding-based inference

For the remaining ~20-30% of variables with ambiguous or terse descriptions (e.g., `MF4` = "RELATIVE WEIGHT, EXAM 1"), use the anchor-propagation approach from the NLS PRD: generate embeddings for variable descriptions, compare to known-classified anchors, and assign concepts above a confidence threshold.

### Phase 4: Manual review of high-value gaps

Expert review of the ~5% of variables that automated methods cannot confidently classify. Priority goes to variables in the most-accessed studies.

### Classification Reproducibility

Classification results must be deterministic and auditable. An identical set of source variables must always produce the identical set of concept assignments, regardless of when or where the pipeline runs.

#### Principle: results are a versioned artifact, not a live computation

```
Source variables (from dbGaP XML)
  ↓ Phase 1: dataset-level rules (version-controlled config)
  ↓ Phase 2: keyword rules (version-controlled patterns)
  ↓ Phase 3: embedding similarity (pinned model + frozen anchors)
  ↓ Phase 4: human review (stored as rules)
  = variable-classifications.json (committed, versioned)
```

Every rebuild produces identical output from the deterministic layers. Non-deterministic layers (embedding, LLM) are invoked only for genuinely new variables, and their output is immediately cached. Nothing is ever re-classified unless explicitly triggered.

#### Determinism controls by phase

**Phases 1-2 (rules)** — Fully deterministic. Dataset-name patterns and keyword rules are stored as versioned config files (JSON or CSV). Same input always produces same output.

**Phase 3 (embeddings)** — Near-deterministic with controls:

- Pin the embedding model version (e.g., `text-embedding-3-small@2024-01-25`, not `latest`)
- Generate anchor embeddings for each of the ~160 concepts once; freeze and version-control them
- Assign the concept with the highest cosine similarity above a threshold
- Use a three-band confidence scheme: cosine > 0.82 = auto-assign, 0.65-0.82 = flag for review, < 0.65 = unclassified
- Store similarity scores alongside assignments for auditability

**Phase 3 fallback (LLM for ambiguous cases)** — Constrained for reproducibility:

- Temperature = 0 and fixed seed parameter to eliminate sampling randomness
- Structured output with constrained decoding — force the model to return one of exactly ~160 valid concept IDs, not free text
- Batch-and-cache: run classification once, store results in a versioned file; the LLM is only invoked for _new_ variables, never to re-classify existing ones
- Optional majority vote (3 runs, take consensus) for borderline cases; log disagreements for human review

**Phase 4 (human review)** — Deterministic by design. Human assignments are stored as explicit rules that feed back into Phase 1/2 config, growing the deterministic layers over time and shrinking the LLM-dependent tail.

#### Drift detection on model upgrades

When the embedding model or LLM version is updated:

1. Re-run classification on the full corpus
2. Diff against the previous `variable-classifications.json`
3. Flag all changed assignments for review before committing the new version
4. This makes model upgrades an explicit, auditable event rather than silent drift

## Variable Modifiers

Rather than multiplying concepts for every combination of measurement context, each concept carries optional **modifiers** — orthogonal annotations that describe _how_ or _in whom_ a variable was measured:

| Modifier         | Values                                                             | Example                                             |
| ---------------- | ------------------------------------------------------------------ | --------------------------------------------------- |
| **Longitudinal** | single time-point, repeated measures                               | Systolic BP measured at 31 Framingham exam cycles   |
| **Generation**   | proband, offspring, parents, siblings, descendants, third-gen      | Framingham Original Cohort vs Offspring vs Gen3     |
| **Method**       | self-report, device-measured, lab assay, imaging, derived/computed | Physical activity by questionnaire vs accelerometer |
| **Specimen**     | serum, plasma, urine, whole blood, saliva, tissue                  | Creatinine in serum vs urine                        |
| **Fasting**      | fasting, non-fasting, unspecified                                  | Fasting glucose vs random glucose                   |

### Why modifiers instead of separate concepts

Without modifiers, supporting "systolic BP in offspring measured longitudinally" would require a combinatorial explosion of concepts (Systolic BP × Original Cohort × Offspring × Gen3 × single × longitudinal = 6+ entries for one measurement). Modifiers keep the concept count at ~160 while still enabling precise queries:

- _"Studies with **longitudinal** blood pressure data"_ — filter on concept = Systolic BP + modifier longitudinal = repeated measures
- _"Accelerometer data in **offspring** cohort"_ — concept = Accelerometer/wearable data + modifier generation = offspring
- _"**Fasting** glucose measurements"_ — concept = Blood glucose + modifier fasting = fasting

Modifiers are populated during classification (Phases 1-4) alongside concept assignment. Dataset-level rules can often infer generation (from dataset name patterns like `ex0_*` = Original, `ex1_*` = Offspring) and longitudinal status (from exam-cycle numbering).

## Ontology Alignment

### Evaluated standards

| Standard    | Top-level categories     | Designed for                 | Covers full dbGaP scope?                               | License  |
| ----------- | ------------------------ | ---------------------------- | ------------------------------------------------------ | -------- |
| SNOMED CT   | 19 meta-categories       | Clinical documentation (EHR) | No (no exposures, omics)                               | Licensed |
| LOINC       | ~280 classes             | Lab/observation workflow     | No (no demographics, exposures)                        | Free     |
| HPO         | 23 organ-system          | Rare disease phenotyping     | No (~40% gap: exposures, diet, activity, omics, admin) | Free     |
| PhenX       | 30 research domains      | Research standardization     | Mostly (no omics, study admin)                         | Free     |
| TOPMed tags | 15 domains / 65 concepts | Cross-study harmonization    | Partially (heart/lung/blood/sleep focus)               | Free     |

None of these standards provides a ready-made ~30-domain taxonomy covering the full breadth of dbGaP variables (clinical measurements, behavioral exposures, omics, study administration). Each was designed for a different purpose.

### Adopted approach: custom domains + UMLS CUI identifiers

Following the precedent set by TOPMed's phenotype tagging system:

1. **Keep the custom ~30 domain / ~160 concept taxonomy** defined above. It covers the full scope of dbGaP data in a way no single formal ontology does.
2. **Map each concept to a UMLS CUI** (Concept Unique Identifier). UMLS is the NIH meta-thesaurus that bridges SNOMED CT, LOINC, MeSH, and ICD simultaneously. TOPMed's 65 concepts already carry CUI assignments that map directly onto ~60 of our ~160 concepts — we extend the pattern to the remaining ~100.
3. **Assign LOINC codes as secondary identifiers** where available. PhenX's 13,653 already-mapped dbGaP variables provide a head start, and the LOINC-SNOMED cooperative ontology bridges both systems.
4. **Use PhenX domain names** where our domains overlap (~22 of 30 PhenX domains) to make the taxonomy familiar to researchers.

### Why UMLS CUIs as the interoperability layer

- **TOPMed already uses them** — 16,671 dbGaP variables tagged with CUI-backed concepts across 17 studies; we inherit this work directly.
- **One CUI bridges multiple code systems** — a single CUI like C2039694 (Systolic blood pressure) maps to SNOMED CT 271649006, LOINC 8480-6, and MeSH D001795.
- **PhenX and dbGaP variables can be linked** — PhenX protocols carry LOINC codes, which map to CUIs, creating a bridge from our taxonomy to 13,653 pre-mapped dbGaP variables.
- **Free and maintained by NLM** — no licensing cost, updated quarterly.

### Example CUI mappings for selected concepts

| Domain          | Concept                 | UMLS CUI | UMLS Term                            |
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

Full CUI assignments for all ~160 concepts will be completed during Phase 1 of the classification pipeline.

## Relationship to NLS PRD

This taxonomy provides the **concept vocabulary** for the Natural Language Search PRD's concept database. Specifically:

- Each concept here becomes a record in the `concepts` OpenSearch index
- The domain hierarchy provides faceted browsing structure
- The classification pipeline (Phases 1-4 above) populates the `mapped_concepts` field on variable records
- TOPMed's 65 existing phenotype tags map directly onto ~60 concepts in this taxonomy

## Open Questions

1. **Granularity tuning** — Should high-throughput omics be one concept per platform (Proteomics) or broken into sub-panels (OLINK Cardiovascular III, OLINK Organ Damage)?
2. **Medication detail** — Should medications be classified by therapeutic area (CV meds, diabetes meds) or as a single concept?
3. ~~**Temporal annotation** — Should concepts carry metadata about whether the study measured them once or longitudinally?~~ **Resolved**: Yes, via the _Longitudinal_ modifier (see Variable Modifiers section above).
4. **Confidence display** — How to present auto-classified concepts vs expert-curated ones in the UI?
5. **Coverage target** — What percentage of variables need classification before we ship? (Recommendation: 90% by volume, which Phase 1 + Phase 2 alone may achieve given the heavy-tailed distribution)
6. **CUI coverage** — How many of the ~160 concepts have clean 1:1 UMLS CUI mappings? TOPMed's 65 are confirmed; the remainder need manual lookup during Phase 1.

## References

- [TOPMed Phenotype Tagging Details](https://topmed.nhlbi.nih.gov/dcc-phenotype-tagging-details) — 65 expert-curated concepts with UMLS CUI mappings
- [TOPMed Phenotype Harmonization (Stilp et al., AJE 2021)](https://academic.oup.com/aje/article/190/10/1977/6228144) — harmonization system and variable tagging methodology
- [PhenX-dbGaP Mapping Paper](https://www.nature.com/articles/s41597-022-01660-4) — 13,653 variables mapped across 521 studies
- [PhenX Toolkit Domains](https://www.phenxtoolkit.org/domains) — 30 research domains for standardized measurement protocols
- [UMLS Semantic Network](https://www.nlm.nih.gov/research/umls/META3_current_semantic_types.html) — 134 semantic types / 15 groups bridging SNOMED CT, LOINC, MeSH, ICD
- [LOINC-SNOMED CT Cooperative Ontology](https://loincsnomed.org/) — joint mapping between observation codes and clinical terms
- [Human Phenotype Ontology](https://hpo.jax.org/) — 23 organ-system phenotype categories (rare disease focus)
- [PRD: Natural Language Search](./PRD-natural-language-search.md) — Parent PRD defining the concept database and search architecture
