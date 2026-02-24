# Variable Concept Classification

You are classifying dbGaP phenotype variables into standardized medical concepts.

## Before Naming: Reason Through These Questions

For EACH variable, work through these questions in your reasoning before assigning a concept:

1. **Subject** — Is this variable about the participant directly, or about a family member/relative?
   → Relative's condition: "Family History of [Condition]" (regardless of which relative — sister, aunt, father all use the same "Family History of" pattern)
   → Relative's demographic attribute: "[Relationship] [Attribute]" (e.g. "Maternal Vital Status", "Sister Birth Year")

2. **Content Type** — Is this a clinical measurement, study administration, or data quality/process metadata?
   → Quality flags (condition codes, interference scores, image quality): "Needs Review"
   → Study administration: use specific admin concept (Participant Identifier, Informed Consent, etc.)

3. **Identifiability** — Can you confidently identify the specific medical concept from the variable name AND description?
   → If the name is opaque AND the description is missing or self-referencing: "Needs Review"
   → If you're guessing based only on the table name: "Needs Review"

4. **Specificity** — Are you naming an instrument/panel/procedure, or the specific measurement from it?
   → Always name the specific measurement (QRS Duration, not Electrocardiography; White Blood Cell Count, not Complete Blood Count)

5. **What to strip vs. what to keep** — Separate study logistics from clinical context.
   → Strip study logistics: visit numbers, exam cycles, "in interim", cohort IDs, method/instrument variants, and measurement-type suffixes (Score, Time, Value, Level, Result).
   → Keep clinical context that changes what is being measured: anatomical location (Lead V6), body position (Sitting, Supine), life stage (during Pregnancy, Gestational), laterality (Left, Right), event timing (at Enrollment, at Diagnosis, at Death), and units/quantities as described (Packs Per Day ≠ Cigarettes Per Day).

6. **Temporality** — Is this about a past diagnosis/event or a current measurement?
   → Past event: "[Condition] History" (e.g. "Hysterectomy History")
   → Pregnancy-specific conditions: use the established clinical term (e.g. "Gestational Diabetes", not "Diabetes History" or "Maternal Diabetes During Pregnancy")
   → Current state: use the measurement name

7. **Condition vs. Treatment** — Is this about a disease/condition, or about medication/treatment for it?
   → These are separate concepts (e.g. "Hypertension History" vs "Antihypertensive Medication Use")

8. **Composite** — Does this variable combine multiple distinct constructs?
   → Classify by the dominant construct (e.g. combined race/ethnicity → "Race")

9. **Behavioral Specificity** — For lifestyle/behavioral variables, what specific aspect is being measured?
   → History, current status, quantity, frequency, and onset/cessation timing are each distinct concepts
   → Timing of exposure is its own concept (e.g. "Smoking Exposure Trimester" for which trimester smoking occurred)

10. **Confidence** — After all the above, are you confident in your assignment?
    → If not: "Needs Review"

## Naming Style

Follow SNOMED CT preferred term conventions, but use Title Case for display:

| Don't Write | Write |
|---|---|
| Thyroid Disease History | Thyroid Disorder History |
| History of High Blood Pressure | Hypertension History |
| Family History of Seizures | Family History of Seizure Disorder |
| Aunt's Seizure History | Family History of Seizure Disorder |
| CBC White Blood Cells | White Blood Cell Count |
| BP Systolic | Systolic Blood Pressure |
| Subject ID Number | Participant Identifier |
| Acute Illness Requiring Medical Attention | Acute Disease |
| Diabetes during pregnancy | Gestational Diabetes |
| Maternal Diabetes During Pregnancy | Gestational Diabetes |

Use natural clinical phrasing, not inverted index forms. Use "disorder" over "disease" for general categories. Use the clinical term, not the colloquial one. No abbreviations in concept names.

## Naming Rules

1. **Use SNOMED CT preferred terms** as the primary source for concept names. Fall back to LOINC long common names for lab/measurement observables.
2. **Title Case** — capitalize each word except prepositions/articles (a, an, and, at, by, for, in, of, on, or, the, to, vs, with).
3. **Classify at the specific measurement level** — a downstream hierarchy builder organizes concepts into categories; your job is to be precise.
4. **Strip study logistics, keep clinical context** — remove visit numbers, exam cycles, "in interim", cohort IDs, method variants, and suffixes like Score/Time/Value. Keep anatomical location, body position, life stage, laterality, event timing (at Enrollment, at Diagnosis), and units as described (Packs ≠ Cigarettes).
5. **Infer from abbreviations** when the description is empty (SBP → Systolic Blood Pressure, FEV1 → Forced Expiratory Volume in 1 Second).

## Granularity Examples

| Too Broad | Just Right | Too Specific |
|---|---|---|
| Blood Pressure | Sitting Systolic Blood Pressure | Sitting Brachial Systolic BP at Visit 3 |
| Blood Pressure | Sitting Diastolic Blood Pressure | Sitting Ankle Diastolic BP Reading 4 |
| Blood Pressure | Antihypertensive Medication Use | Currently Taking BP Med Visit 4 |
| Smoking | Current Smoking Status | Currently Smoke Cigarettes |
| Smoking | Cigarettes Per Day | Avg Cigarettes Smoked Per Day |
| Smoking | Smoking Exposure Trimester | Trimester of Smoking at Visit 2 |
| Electrocardiography | QRS Duration | QRS Duration Lead V5 Visit 3 |
| Electrocardiography | QT Interval | Corrected QT Bazett Exam 7 |
| Electrocardiography | PR Interval | PR Interval Lead II Visit 1 |
| Electrocardiography | T-Wave Amplitude in Lead V6 | T Wave Amplitude in Lead V6 Visit 3 |
| Complete Blood Count | White Blood Cell Count | WBC Automated Count Visit 4 |
| Complete Blood Count | Hemoglobin | Hemoglobin Level at Baseline |
| Complete Blood Count | Platelet Count | Platelet Count Automated Visit 3 |
| Urinalysis | Urine Albumin | 24-Hour Urine Albumin Visit 3 |
| Lipids | LDL Cholesterol | Direct LDL Friedewald |
| Cognition | Trail Making Test Part B | Trail Making Part B Time Visit 2 |
| Cognition | Digit Span Forward | Digit Span Forward Score Visit 3 |
| Echocardiography | Left Ventricular Ejection Fraction | Biplane Simpson LVEF Visit 2 |
| Diabetes | Gestational Diabetes | Maternal Diabetes During Pregnancy Visit 1 |
| Study Administration | Participant Identifier | Dummy ID for Eye Disease Cohort |
| Study Administration | Informed Consent | Consent Group Description |
| Study Administration | Follow-Up Duration | Years from Randomization to Visit |

The middle column is the target level.
