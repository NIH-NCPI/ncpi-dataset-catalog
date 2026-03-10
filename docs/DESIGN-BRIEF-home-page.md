# Design Brief: Home Page

> For: Kaspars | Status: DRAFT — Mar 2026
> Refs: [DESIGN-BRIEF-research-mode.md](DESIGN-BRIEF-research-mode.md) · cc-design #298

---

## Problems to Solve

1. **It's not obvious what this site is.** A new user lands on a platform table with no explanation. We need to clearly state: this site lets you search dbGaP studies using natural language across study metadata, hundreds of thousands of semantically harmonized variables, and consent codes.

2. **It's not obvious where the data lives.** The catalog links studies back to datasets hosted on four NIH cloud platforms — [AnVIL](https://anvilproject.org/), [BDC](https://biodatacatalyst.nhlbi.nih.gov/), [CRDC](https://datacommons.cancer.gov/), and [KFDRC](https://kidsfirstdrc.org/). This "connector" role needs to be visible on the home page.

3. **It's not obvious what the catalog adds.** Each study page associates studies with selected publications, hundreds of thousands of semantically harmonized variables (what was measured), demographic distributions (sex, race/ethnicity), and genetically inferred ancestry — enrichments that don't exist in dbGaP search alone.

4. **It's not obvious how to get access to data.** Researchers can apply for subject-level access through [dbGaP](https://dbgap.ncbi.nlm.nih.gov/) or the Broad's [DUOS](https://duos.broadinstitute.org/) system. This should be visible, not buried.

---

## Positioning

**The NCPI Dataset Catalog is a connector** — it sits between dbGaP's metadata and the NIH cloud platforms where the data lives. It makes dbGaP content searchable with natural language and links you to the right platform to access the data.

It is _not_ a data repository itself. It helps you find studies, understand what they measured, and get to the data.

---

## Page Sections

### 1. Value Statement (above the fold)

One sentence that tells a new visitor what this is:

> Search dbGaP studies with natural language — across study metadata, semantically harmonized variables, disease hierarchies, and consent codes — then apply for access or view the study on its cloud platform.

This should be the first thing you read. No jargon beyond the platform names (which are explained by logos + links).

### 2. Search Input (primary CTA)

Large text input below the value statement. Submitting navigates to `/research/studies` with the query as the first message.

- **Placeholder**: "Describe what you're looking for — e.g., cardiovascular studies with whole genome sequencing"
- **Example chips** below the input (clickable, pre-fill and submit):
  - "Diabetes studies with whole genome sequencing"
  - "Pediatric cancer on KFDRC"
  - "Studies measuring blood pressure and BMI consented for for-profit use with no review board"
  - "Cardiovascular studies measuring calcium or cholesterol"
  - "All variables measuring chocolate consumption"
- **Fallback**: "Or [browse all studies](/studies) directly"

All example queries must return useful results with the current search pipeline.

### 3. Key Capabilities

Semantic, AI-powered search across:

- **Study metadata** — descriptions, data types, study designs, platforms
- **Harmonized variables** — hundreds of thousands of dbGaP variables semantically classified into canonical measurement concepts across 20 domains: Biomarkers, Anthropometry, Imaging, Respiratory, Disease Events, Medications, Substance Use, Diet, Exercise, Sleep, Demographics, Race & Ethnicity, Ancestry, Geography, Socioeconomic, Reproductive Health, Environment, Mental Health, General Health, and Study Administration
- **MeSH disease hierarchy** — disease focus terms organized by the NLM Medical Subject Headings tree, so searching "Neoplasms" returns all descendant cancer types
- **Consent codes** — GA4GH consent categories (GRU, HMB, DS, etc.) so researchers can filter by data use restrictions
- **Inferred ancestry** — genetically computed ancestry groups from dbGaP
- **Demographics** — self-reported sex and race/ethnicity distributions

### 4. What's in the Catalog (key numbers)

Prominent stats that communicate scale:

| Stat               | Value                                          |
| ------------------ | ---------------------------------------------- |
| Studies            | thousands of dbGaP studies                     |
| Measured variables | hundreds of thousands, semantically harmonized |
| Disease focus      | searchable via MeSH disease hierarchy          |
| Platforms          | 4 (AnVIL, BDC, CRDC, KFDRC)                    |

### 5. What Each Study Includes

Brief list of what the catalog associates with each study — this is the "what do I get" section:

- **Study metadata** — description, disease focus (searchable via MeSH hierarchy), study design, data types, consent codes
- **Selected publications** — PI-curated references with citation counts
- **Measured variables** — hundreds of thousands of variables semantically harmonized into canonical concepts, linked to dbGaP variable records
- **Demographics** — sex, race/ethnicity, and genetically inferred ancestry distributions

### 6. Connected Platforms

Show the four platform logos with one-line descriptions and links. This makes the "connector" role concrete:

- **dbGaP** — NCBI Database of Genotypes and Phenotypes ([dbgap.ncbi.nlm.nih.gov](https://dbgap.ncbi.nlm.nih.gov/))
- **AnVIL** — NHGRI Genomic Data Science ([anvilproject.org](https://anvilproject.org/))
- **BDC** — NHLBI BioData Catalyst ([biodatacatalyst.nhlbi.nih.gov](https://biodatacatalyst.nhlbi.nih.gov/))
- **CRDC** — NCI Cancer Research Data Commons ([datacommons.cancer.gov](https://datacommons.cancer.gov/))
- **KFDRC** — Kids First Data Resource Center ([kidsfirstdrc.org](https://kidsfirstdrc.org/))

### 7. How to Access Data

Short section — two paths:

- **dbGaP** — apply for authorized access at [dbgap.ncbi.nlm.nih.gov](https://dbgap.ncbi.nlm.nih.gov/)
- **DUOS** — request access through the Broad Institute's Data Use Oversight System at [duos.broadinstitute.org](https://duos.broadinstitute.org/)

One line: "The catalog uses only publicly available metadata — no subject-level data. To work with individual-level data, apply for access through dbGaP or DUOS."

---

## Transition: Home → Research Mode

When the user submits a query (typed or from a chip):

1. Navigate to `/research/studies`
2. Query appears as the first chat message
3. System starts processing immediately (thinking indicator)
4. Browser back returns to home page

This is a route change, not an in-place morph. The home page is a landing page; Research Mode is a workspace.

---

## Constraints

- **Example queries must work** — test each chip against the current search pipeline before shipping
- **Beta disclaimer** — subtle note (footer or small banner), not prominent enough to scare users away
- **Footer** — include Clever Canary logo
- **Keep it light** — one screen, minimal scrolling, fast to scan

---

## Visual References

| Reference             | What to look at                                      |
| --------------------- | ---------------------------------------------------- |
| Claude.ai home        | Hero input + example prompts → transitions into chat |
| ChatGPT home          | Same pattern — input + example chips                 |
| Hugging Face datasets | Stats summary + search input                         |
