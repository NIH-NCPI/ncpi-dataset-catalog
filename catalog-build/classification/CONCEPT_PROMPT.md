# Variable Concept Classification

You are classifying individual dbGaP phenotype variables into standardized medical concepts.

For each variable (given as `name: description`), return the most appropriate standard medical concept name.

## Naming Rules

1. **Use standard medical terminology** — prefer terms as they appear in MeSH, LOINC, or UMLS.
2. **Title Case** — always capitalize concept names (e.g. "Systolic Blood Pressure").
3. **Be specific but not too specific** — see the granularity table below.
4. **Strip qualifiers** — remove visit numbers, time points, study-specific prefixes, and cohort identifiers from the concept. The concept should be the underlying measurement, not the occasion.
5. **Derived/weight/flag variables** get the same concept as the underlying measurement (e.g. a weight variable for an IMT measurement → "Carotid Intima-Media Thickness").
6. **Administrative/ID variables** → "Study Administration" (subject IDs, sample IDs, consent group, visit indicator, center, form version, etc.).
7. **Demographics** → use the specific concept: "Age", "Sex", "Race/Ethnicity", "Education", "Marital Status", etc. Do NOT lump them under "Demographics".
8. **Medication use** → "Medication Use" (generic) or the specific class if clear (e.g. "Antihypertensive Medication Use").
9. **Medical history** → "Medical History" (generic) or specific condition if clear (e.g. "Diabetes History").
10. **If the description is empty or opaque**, infer from the variable name using standard abbreviation knowledge (e.g. SBP = Systolic Blood Pressure, FEV = Forced Expiratory Volume).

## Granularity Examples

| Too Broad | Just Right | Too Specific |
|---|---|---|
| Blood Pressure | Systolic Blood Pressure | Supine Brachial Systolic Blood Pressure at Visit 3 |
| Blood Pressure | Diastolic Blood Pressure | Ankle Diastolic Blood Pressure Reading 4 |
| Imaging | Carotid Intima-Media Thickness | Left Bifurcation Far Wall Average Thickness |
| Lung Function | Forced Expiratory Volume | FEV1 Percent Predicted at Visit 2 |
| Blood Test | Complete Blood Count | Mean Corpuscular Volume |
| Lipids | LDL Cholesterol | Direct LDL Cholesterol Friedewald |
| Heart | Electrocardiography | PR Interval |
| Bone | Bone Mineral Density | Femoral Neck T-Score |

The middle column is the target level. Concept names should identify the measurement or test — not the individual parameter or the broad category.

## Important Edge Cases

- **Ankle-Brachial Index**: Use "Ankle-Brachial Index" — it is its own measurement, not just "Blood Pressure".
- **Plaque presence/absence**: Use "Carotid Plaque" (not IMT — plaque grading is a distinct assessment).
- **Apolipoprotein assays**: Use "Apolipoprotein A-I", "Apolipoprotein B", etc.
- **Hematology panels (CBC)**: Use "Complete Blood Count" for WBC, RBC, hemoglobin, hematocrit, platelets, MCV, MCH, MCHC, RDW.
- **Metabolic panels**: Use "Basic Metabolic Panel" or "Comprehensive Metabolic Panel" as appropriate.
- **Urinalysis variables**: Use "Urinalysis".
- **Body measurements**: Use specific names — "Body Mass Index", "Waist Circumference", "Height", "Weight".
- **Smoking/alcohol**: Use "Smoking Status", "Alcohol Use", etc.
- **Pacemaker flags in ECG tables**: These are still "Electrocardiography" (they describe ECG findings).
