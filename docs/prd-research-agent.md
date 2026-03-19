# PRD: Research Agent

## Origin

This PRD was generated from a live session where a user posed a research question and an agent (Claude with MCP catalog tools) answered it interactively. The session revealed a repeatable pattern that could be automated into a dedicated research agent.

---

## The Research Question

> "I'm interested in studying the effect of alcohol consumption on cancer recurrence rates and if this varies across cancer types or computed ancestry. What datasets do we have that can help me find out?"

## Tool Call History

### Step 1: Decompose the question into searchable facets

The question contains several concepts that map to different catalog facets:

| Concept from question          | Facet            | Search term          |
| ------------------------------ | ---------------- | -------------------- |
| alcohol consumption            | measurement      | "alcohol"            |
| cancer (disease context)       | focus            | "cancer", "neoplasm" |
| recurrence rates               | measurement      | "recurrence"         |
| cancer types                   | focus            | (already covered)    |
| computed ancestry (stratifier) | computedAncestry | (list all values)    |

**Calls made (parallel where possible):**

```
search_concepts(query="alcohol consumption", facet="measurement")  -> [] (too specific)
search_concepts(query="cancer", facet="focus")                     -> 8 results (specific cancers)
search_concepts(query="recurrence", facet="measurement")           -> 2 results (status + time)
```

**Observation:** "alcohol consumption" returned nothing — too specific. The agent broadened to "alcohol":

```
search_concepts(query="alcohol", facet="measurement")              -> 20 results (lifetime use, 30-day, FFQ, etc.)
search_concepts(query="neoplasm", facet="focus")                   -> 20 results (broad MeSH hierarchy)
search_concepts(query="oncology", facet="focus")                   -> [] (not a MeSH term in catalog)
```

### Step 2: Query for studies at the intersection

Using the top-level concepts discovered in Step 1:

```
search_studies(
    measurement=["phenx:alcohol_lifetime_use",
                 "phenx:alcohol_30day_quantity_and_frequency",
                 "ncpi:cancer_diagnosis_cancer_outcomes_survival_recurrence_status"],
    focus=["Neoplasms"]
) -> 47 studies
```

### Step 3: Check stratifier availability

```
list_facet_values(facet="computedAncestry") -> 9 ancestry categories, 300-456 studies each
```

This confirmed that ancestry stratification is broadly available across the catalog.

---

## Analysis of the Tool Call Pattern

### Phase 1: Concept Discovery

**Goal:** Translate natural-language research concepts into catalog facet values.

**Method:**

1. Extract key concepts from the question (alcohol, cancer, recurrence, ancestry)
2. Map each concept to its most likely facet (measurement, focus, computedAncestry)
3. Search for each concept within its facet
4. If a search returns nothing, broaden the term (e.g., "alcohol consumption" -> "alcohol")
5. If a search returns too many results, note the top-level parent concepts for the study query

**Key decisions:**

- The agent chose `phenx:alcohol_lifetime_use` and `phenx:alcohol_30day_quantity_and_frequency` as the most relevant alcohol measurements (highest study counts: 71 and 55)
- The agent chose `Neoplasms` as the broadest cancer focus (1,028 studies) rather than specific cancer types, since the user wanted to compare _across_ cancer types
- The agent chose `ncpi:cancer_diagnosis_cancer_outcomes_survival_recurrence_status` (28 studies) as the recurrence outcome variable

### Phase 2: Intersection Query

**Goal:** Find studies that have ALL required data elements simultaneously.

**Method:**

- AND the measurement concepts together (studies must measure alcohol AND recurrence)
- AND with the focus facet (studies must be cancer-focused)
- Values within a facet are OR-ed (alcohol_lifetime_use OR alcohol_30day works)

**Result:** 47 studies at the intersection.

### Phase 3: Stratifier Check

**Goal:** Verify the user's stratification variables are available.

**Method:**

- List all values for the stratifier facet
- Cross-reference study counts to estimate coverage

**Result:** Computed ancestry has 9 categories with broad coverage (300+ studies each), confirming feasibility.

### Phase 4: Result Synthesis

**Goal:** Turn raw study lists into actionable research guidance.

**Components of the summary:**

| Component               | Example                                                                        | Purpose                                                    |
| ----------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| **Top-line count**      | "47 studies"                                                                   | Immediate feasibility signal                               |
| **Highlighted studies** | PAGE Multiethnic Cohort (27,995 participants)                                  | Surface the best candidates by size, design, and relevance |
| **Cancer type spread**  | "breast, colorectal, prostate, pancreatic..."                                  | Confirm cross-type comparison is possible                  |
| **Stratifier coverage** | "9 ancestry categories, 300-456 studies each"                                  | Confirm the user's stratification axis is available        |
| **Caveats**             | "alcohol measurement is lifetime use, not deeply phenotyped drinking patterns" | Manage expectations about data depth                       |
| **Power warnings**      | "smaller tumor studies (10-50 participants) are likely underpowered"           | Steer user toward actionable datasets                      |

---

## Generalizable Method

The interaction follows a **four-phase pattern** that a research agent could automate:

```
1. DECOMPOSE  — Parse the research question into searchable concepts
                 (exposure, outcome, disease context, stratifiers)

2. DISCOVER   — For each concept, search the catalog to find matching
                 facet values. Broaden terms if initial search fails.
                 Select the most relevant values by study count and
                 semantic fit.

3. INTERSECT  — Query for studies/variables at the intersection of
                 all required concepts. This is the core feasibility
                 check: "do datasets exist with ALL the data I need?"

4. SYNTHESIZE — Rank results by fitness for the research question.
                 Highlight top candidates, note coverage gaps, flag
                 caveats about data depth or statistical power.
```

### What the agent did well

- **Broadening failed searches** ("alcohol consumption" -> "alcohol") without losing specificity
- **Choosing the right abstraction level** (broad "Neoplasms" for cross-type comparison vs. specific cancer types)
- **Parallel concept discovery** (searched alcohol, cancer, recurrence simultaneously)
- **Proactive stratifier check** (verified ancestry coverage without being explicitly asked to query it)
- **Contextualized synthesis** (didn't just list 47 studies — highlighted the ones most useful for the specific question)

### What could be improved

- **No variable-level drill-down** — the agent didn't check what specific alcohol variables exist in the top candidate studies (e.g., does PAGE MEC have drinks-per-week or just ever/never?)
- **No consent filtering** — some studies have disease-specific consent codes (DS-CA, DS-BRCA) that may restrict use to specific cancer research
- **No cross-referencing** — didn't check which of the 47 studies actually have computed ancestry data (the ancestry facet counts are catalog-wide, not specific to the 47)
- **No power analysis** — could estimate feasibility by aggregating participant counts across the matching studies
- **No data type guidance** — didn't note which studies have genomic data (WGS/WXS) vs. phenotype-only, which matters for genetic ancestry analysis

---

## Open Questions

1. Should the research agent call the LLM pipeline (extract + resolve) to decompose the question, or use a lighter-weight extraction?
2. How should the agent handle ambiguous concepts (e.g., "alcohol" maps to 20+ measurement concepts — which ones matter for the question)?
3. Should the agent produce a structured "research feasibility report" or a conversational summary?
4. How deep should the variable-level drill-down go? Checking every variable in 47 studies is expensive.
5. Should consent eligibility be checked automatically? (The `compute_consent_eligibility` MCP tool exists for this.)
