# Variable Concept Classification

You are classifying individual dbGaP phenotype variables into standardized medical concepts.

For each variable (given as `name: description`), return the most appropriate standard medical concept name.

## Naming Rules

1. **Use UMLS preferred concept names** — return the UMLS Metathesaurus preferred name for the concept whenever possible. These are the canonical names from SNOMED CT, MeSH, or LOINC as unified in UMLS (e.g. "Diastolic blood pressure", "Age at smoking cessation", "Cigarette smoking").
2. **Title Case** — always capitalize concept names (e.g. "Systolic Blood Pressure").
3. **Be specific but not too specific** — see the granularity table below. When a domain has meaningfully different aspects (history, current status, quantity, timing, medication), classify to the specific aspect — not the umbrella category.
4. **Strip qualifiers** — remove visit numbers, time points, study-specific prefixes, and cohort identifiers from the concept. The concept should be the underlying measurement, not the occasion.
5. **Derived/weight/flag variables** get the same concept as the underlying measurement (e.g. a weight variable for an IMT measurement → "Carotid Intima-Media Thickness").
6. **Administrative/ID variables** → use the specific administrative concept (e.g. what kind of ID, what aspect of study design). Do NOT lump them all under "Study Administration".
7. **Demographics** → use the specific concept: "Age", "Sex", "Race/Ethnicity", "Education", "Marital Status", etc. Do NOT lump them under "Demographics".
8. **Medication use** → "Medication Use" (generic) or the specific class if clear (e.g. "Antihypertensive Medication Use").
9. **Medical history** → always use the specific condition (e.g. "Hysterectomy History", "Diabetes History", "Intermittent Claudication"). Only use "Medical History" if the description is truly generic (e.g. "illness", "hospitalization") with no identifiable condition.
10. **If the description is empty or opaque**, infer from the variable name using standard abbreviation knowledge (e.g. SBP = Systolic Blood Pressure, FEV = Forced Expiratory Volume).

## Granularity Examples

| Too Broad | Just Right | Too Specific |
|---|---|---|
| Blood Pressure | Systolic Blood Pressure | Supine Brachial Systolic Blood Pressure at Visit 3 |
| Blood Pressure | Diastolic Blood Pressure | Ankle Diastolic Blood Pressure Reading 4 |
| Blood Pressure | Hypertension History | History of High Blood Pressure at Baseline |
| Blood Pressure | Antihypertensive Medication Use | Currently Taking BP Medication Visit 4 |
| Smoking | Current Smoking Status | Currently Smoke Cigarettes |
| Smoking | Cigarettes Per Day | Average Number of Cigarettes Smoked Per Day |
| Alcohol | Alcohol Consumption Frequency | Days Per Week Drinking at Visit 2 |
| Imaging | Carotid Intima-Media Thickness | Left Bifurcation Far Wall Average Thickness |
| Lung Function | Forced Expiratory Volume | FEV1 Percent Predicted at Visit 2 |
| Blood Test | Complete Blood Count | Mean Corpuscular Volume |
| Lipids | LDL Cholesterol | Direct LDL Cholesterol Friedewald |
| Heart | Electrocardiography | PR Interval |
| Bone | Bone Mineral Density | Femoral Neck T-Score |
| Study Administration | Participant Identifier | Dummy ID Number for Eye Disease Cohort |
| Study Administration | Informed Consent | Consent Group Description |
| Study Administration | Treatment Assignment | AREDS Treatment Arm at Visit 5 |
| Study Administration | Follow-Up Duration | Years from Randomization to Visit |

The middle column is the target level. Concept names should identify the measurement or test — not the individual parameter or the broad category.

## Important Edge Cases

- **Ankle-Brachial Index**: Use "Ankle-Brachial Index" — it is its own measurement, not just "Blood Pressure".
- **Plaque presence/absence**: Use "Carotid Plaque" (not IMT — plaque grading is a distinct assessment).
- **Apolipoprotein assays**: Use "Apolipoprotein A-I", "Apolipoprotein B", etc.
- **Hematology panels (CBC)**: Use "Complete Blood Count" for WBC, RBC, hemoglobin, hematocrit, platelets, MCV, MCH, MCHC, RDW.
- **Metabolic panels**: Use "Basic Metabolic Panel" or "Comprehensive Metabolic Panel" as appropriate.
- **Urinalysis variables**: Use "Urinalysis".
- **Body measurements**: Use specific names — "Body Mass Index", "Waist Circumference", "Height", "Weight".
- **Behavioral exposures (smoking, alcohol, diet, exercise)**: Distinguish the specific aspect being measured — history, current status, quantity, frequency, onset/cessation timing are all different concepts. Do NOT lump them under one umbrella (e.g. do not put all smoking variables under "Smoking Status").
- **Pacemaker flags in ECG tables**: These are still "Electrocardiography" (they describe ECG findings).
