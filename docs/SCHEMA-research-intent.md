# Research Intent Schema

> Baseline PICOT-based schema for capturing structured research intent from natural-language conversations.
> Status: DRAFT — Feb 2026

---

## Overview

When a user describes their research question, the system parses it into a structured **intent object**. This object drives dataset filtering, variable matching, and workflow suggestions. The schema is PICOT-based with extension points for domain-specific modules (GWAS, eQTL, DEG, etc.).

## Baseline Schema

```jsonc
{
  // --- Meta ---
  "intent_type": "observational", // see Intent Types below
  "confidence": 0.0, // 0–1, how complete/confident the parse is
  "unfilled_slots": ["demographics.ancestry", "outcomes[0].time_window"],

  // --- P: Population ---
  "population": {
    "condition_focus": [], // e.g. ["type 2 diabetes", "cardiovascular disease"]
    "demographics": {
      "age_range": null, // e.g. [18, 65] or "pediatric" | "adult" | "geriatric"
      "sex": null, // "male" | "female" | "both" | null
      "ancestry": null, // e.g. ["African", "European"] or null
    },
    "minimum_sample_size": null, // e.g. 1000
  },

  // --- I/E: Intervention or Exposure ---
  "exposure": {
    "concept": null, // e.g. "cigarette smoking"
    "operationalization": [], // how the exposure must be measured in the data
    // each entry: { "measurement": str, "role": "primary"|"alternative", "threshold": any? }
  },
  "intervention": null, // same structure as exposure; null if purely observational
  // intervention: { "concept": str, "operationalization": [{ "measurement": str, ... }] }

  // --- C: Comparator ---
  "comparator": {
    "type": null, // e.g. "smoking strata", "treated vs untreated"
    "levels": [], // e.g. ["never", "former", "current"]
  },

  // --- O: Outcomes ---
  "outcomes": [],
  // each entry:
  // {
  //   "concept": str,                   // e.g. "glycemic response"
  //   "operationalization": [{
  //     "measurement": str,             // e.g. "HbA1c"
  //     "delta": bool,                  // change from baseline?
  //     "time_window": str?             // e.g. "baseline_to_6_months"
  //   }],
  //   "priority": "primary" | "secondary" | "exploratory"
  // }

  // --- T: Time ---
  "time": {
    "design_requirement": null, // "longitudinal" | "cross-sectional" | null
    "timepoints_required": [], // e.g. ["baseline", "follow-up"]
    "minimum_follow_up": null, // e.g. "6 months", "2 years"
  },

  // --- Covariates (confounders / adjustment variables) ---
  "covariates": [], // e.g. ["baseline BMI", "age", "sex", "concomitant meds"]

  // --- Data Requirements (context / platform constraints) ---
  "data_requirements": {
    "study_design": [], // e.g. ["observational cohort", "RCT"]
    "platforms": [], // e.g. ["BDC", "AnVIL"] — empty means any
    "consent_codes": [], // e.g. ["GRU", "HMB"] — empty means any
    "genomic_data_types": [], // e.g. ["WGS", "genotype array"]
    "molecular_data_types": [], // e.g. ["RNA-Seq", "methylation array"]
    "tissue_sites": [], // e.g. ["whole blood", "pancreas"]
  },

  // --- Extension module (null for baseline) ---
  "module": null,
  // see Domain Modules below
}
```

## Intent Types

The `intent_type` field determines how the system interprets the question and which slots are required vs optional.

| Intent Type                     | Description                             | Required Slots | Optional Slots   |
| ------------------------------- | --------------------------------------- | -------------- | ---------------- |
| `observational`                 | Basic "find datasets matching criteria" | P              | all others       |
| `exposure_outcome`              | Does exposure X affect outcome Y?       | P, E, O        | C, T, covariates |
| `treatment_effect`              | Effect of intervention on outcome       | P, I, O        | C, T, covariates |
| `treatment_effect_modification` | Does factor X modify treatment effect?  | P, I, E, C, O  | T, covariates    |
| `prevalence`                    | How common is X in population Y?        | P, O           | T                |
| `exploratory`                   | "What's here?" — no specific hypothesis | (none)         | all              |

## Operationalization Pattern

Both exposures and outcomes use the same sub-structure for specifying _how_ a concept must be measured in the data:

```jsonc
{
  "measurement": "pack-years", // variable concept name
  "role": "primary", // "primary" | "alternative" — for exposure
  "priority": "primary", // "primary" | "secondary" | "exploratory" — for outcome
  "delta": false, // does the analysis need change-from-baseline?
  "threshold": null, // e.g. ">= 10" — for inclusion criteria
  "time_window": null, // e.g. "baseline_to_6_months"
  "optional": false, // nice-to-have vs must-have
  "examples": [], // e.g. ["semaglutide", "liraglutide"] — value-level hints
}
```

## Domain Modules (future)

The `module` field holds domain-specific extensions. Each module adds slots that make sense for that analysis type.

### GWAS Module

```jsonc
{
  "module": {
    "type": "gwas",
    "trait": "HbA1c", // the GWAS phenotype
    "trait_type": "quantitative", // "quantitative" | "binary" | "survival"
    "ancestry_specific": true, // single-ancestry or trans-ethnic
    "imputation_panel": null, // e.g. "TOPMed", "HRC"
    "minimum_variants": null, // e.g. 5000000
    "summary_stats_only": false, // can we use published GWAS sumstats?
  },
}
```

### eQTL Module

```jsonc
{
  "module": {
    "type": "eqtl",
    "target_genes": [], // e.g. ["TCF7L2", "SLC30A8"]
    "tissue_sites": ["pancreatic islets", "liver"],
    "cis_or_trans": "cis", // "cis" | "trans" | "both"
    "requires_genotype_and_expression": true,
  },
}
```

### Differential Expression Module

```jsonc
{
  "module": {
    "type": "differential_expression",
    "contrast": {
      // what groups to compare
      "condition": ["T2D", "control"],
      "tissue": "pancreatic islets",
    },
    "expression_platform": [], // e.g. ["RNA-Seq", "scRNA-Seq"]
    "minimum_samples_per_group": null,
    "covariates_in_model": [], // e.g. ["age", "sex", "batch"]
  },
}
```

### Meta-Analysis Module

```jsonc
{
  "module": {
    "type": "meta_analysis",
    "requires_multiple_cohorts": true,
    "harmonization": "required", // "required" | "preferred" | "not_needed"
    "effect_type": "fixed", // "fixed" | "random"
    "minimum_studies": 3,
  },
}
```

---

## Slot Filling Behavior

How the system uses unfilled slots in conversation:

| Scenario                      | System behavior                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| User provides P only          | Show matching studies; ask about E/O: "What are you measuring in these populations?"                                            |
| P + E filled, no O            | "You mentioned smoking as an exposure — what outcome are you interested in? Lung function, cancer risk, cardiovascular events?" |
| P + O filled, no E            | "What factor do you think influences [outcome]?"                                                                                |
| All PICOT filled              | Show ranked results; suggest workflows; highlight best-match studies                                                            |
| `intent_type` = `exploratory` | Skip slot-filling; return facet distributions and summaries                                                                     |

The system should **never block on unfilled slots** — partial intent always returns results. Unfilled slots trigger gentle prompts, not errors.

---

## Example: Full Intent Object

"I'm studying whether smoking modifies the effect of GLP-1 agonists on glycemic control in T2D patients."

```json
{
  "intent_type": "treatment_effect_modification",
  "confidence": 0.85,
  "unfilled_slots": [
    "population.demographics.ancestry",
    "time.minimum_follow_up"
  ],

  "population": {
    "condition_focus": ["type 2 diabetes"],
    "demographics": {
      "age_range": null,
      "sex": null,
      "ancestry": null
    },
    "minimum_sample_size": null
  },

  "exposure": {
    "concept": "cigarette smoking",
    "operationalization": [
      { "measurement": "pack-years", "role": "primary", "threshold": null },
      {
        "measurement": "current/former/never",
        "role": "alternative",
        "threshold": null
      }
    ]
  },

  "intervention": {
    "concept": "GLP-1 receptor agonists",
    "operationalization": [
      {
        "measurement": "medication name",
        "examples": ["semaglutide", "liraglutide"]
      },
      { "measurement": "dose", "optional": true },
      { "measurement": "start date", "optional": true }
    ]
  },

  "comparator": {
    "type": "smoking strata",
    "levels": ["never", "former", "current"]
  },

  "outcomes": [
    {
      "concept": "glycemic response",
      "operationalization": [
        {
          "measurement": "HbA1c",
          "delta": true,
          "time_window": "baseline_to_3-6_months"
        }
      ],
      "priority": "primary"
    },
    {
      "concept": "weight response",
      "operationalization": [
        {
          "measurement": "weight",
          "delta": true,
          "time_window": "baseline_to_3-12_months"
        }
      ],
      "priority": "secondary"
    }
  ],

  "time": {
    "design_requirement": "longitudinal",
    "timepoints_required": ["baseline", "follow-up"],
    "minimum_follow_up": null
  },

  "covariates": [
    "baseline HbA1c",
    "baseline BMI",
    "age",
    "sex",
    "ancestry",
    "comorbidities",
    "concomitant meds"
  ],

  "data_requirements": {
    "study_design": ["observational cohort", "RCT"],
    "platforms": [],
    "consent_codes": [],
    "genomic_data_types": ["genotype array", "WGS", "WES"],
    "molecular_data_types": [],
    "tissue_sites": []
  },

  "module": null
}
```

---

## Mapping Intent to Catalog Queries

| Intent field                                  | Catalog query                                                |
| --------------------------------------------- | ------------------------------------------------------------ |
| `population.condition_focus`                  | `focus` facet (semantic match)                               |
| `population.demographics`                     | Future demographics facets (age, sex, ancestry)              |
| `population.minimum_sample_size`              | `participantCount >= N`                                      |
| `exposure.concept`                            | `measurement` facet (variable-level match)                   |
| `exposure.operationalization[].measurement`   | Variable concept match (requires variable-level index)       |
| `intervention.concept`                        | `measurement` facet (variable-level match)                   |
| `comparator.levels`                           | Variable value-level match (deepest — requires coded values) |
| `outcomes[].operationalization[].measurement` | `measurement` facet (variable-level match)                   |
| `time.design_requirement`                     | `studyDesign` facet                                          |
| `data_requirements.study_design`              | `studyDesign` facet                                          |
| `data_requirements.platforms`                 | `platform` facet                                             |
| `data_requirements.consent_codes`             | `consentCode` facet                                          |
| `data_requirements.genomic_data_types`        | `dataType` facet                                             |

### Match depth tiers

1. **Study-level** (available now): P (condition_focus), T (study_design), data_requirements (platform, consent, dataType)
2. **Variable-level** (concept pipeline): E/O (measurement concepts), covariates
3. **Value-level** (future): C (comparator levels — does the variable have the right coded categories?)
