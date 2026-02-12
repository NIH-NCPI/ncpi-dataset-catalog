# PRD: Concept Database for dbGaP Variable Harmonization

## Overview

This document defines the requirements for building a comprehensive discovery layer over dbGaP (database of Genotypes and Phenotypes). The system will enable researchers to:

1. **Query across all dbGaP studies** — not just those hosted on specific cloud platforms
2. **Search variables by concept** — finding all variables measuring the same thing regardless of naming conventions
3. **Discover research context** — understanding both the original research that produced the data and secondary analyses that reused it

The concept database will use OpenSearch to provide exact match, synonym lookup, and fuzzy matching on phenotype terms, mapping them to standardized concept codes and clustered variable groups.

## Problem Statement

### The Core Problem: No Unified Search Across Studies AND Variables

Researchers need to answer questions like:

- _"Which studies have systolic blood pressure data I can use for my cardiovascular analysis?"_
- _"What diabetes-related variables exist across all of dbGaP, and which studies contain them?"_
- _"Find me studies with both BMI and smoking status variables"_

**Today, this is impossible.** dbGaP allows searching studies OR variables, but not the combined query: _"Show me all studies that have variables matching concept X."_ Researchers must manually browse each study's variable list—an impractical task across 3,000 studies.

### Gap 1: Incomplete Study Coverage

The NCPI Dataset Catalog currently aggregates studies from four cloud platforms (AnVIL, BDC, CRDC, KFDRC), but this represents only a subset of the ~3,000 studies in dbGaP. Researchers need visibility into ALL dbGaP studies to understand the full landscape of available data.

### Gap 2: Variable Naming Inconsistency

dbGaP contains ~340,000 unique phenotype variables across ~2,700 studies. Each study uses its own naming conventions:

- "systolic blood pressure" vs "SBP" vs "bp_sys" vs "SYSBP" all mean the same thing
- No way to search by concept and get all matching variables across all studies
- Cross-study analysis requires manual curation of variable mappings

Existing harmonization efforts (TOPMed, PhenX) have mapped only ~1.5% of variables to standard concepts. This data is fragmented and not integrated into a searchable system.

### Gap 3: Research Context

dbGaP provides data but limited context about:

- **Original research**: What protocols were used? What were the study's primary findings?
- **Secondary use**: What other researchers have used this data? What did they discover?

Without this context, researchers struggle to understand if a dataset is appropriate for their needs.

## Goals

1. **Complete dbGaP Coverage**: Include all ~3,000 dbGaP studies, not just platform-hosted ones
2. **Unified Concept Search**: Enable searching by variable name, description, or concept term to find all related dbGaP variables
3. **Synonym Support**: Return matches for synonymous terms (e.g., "BP" → "blood pressure")
4. **Concept Clustering**: Group variables that measure the same underlying concept
5. **Standard Code Mapping**: Link variables to UMLS CUI, LOINC, and other standard vocabularies
6. **Publication Discovery**: Surface papers describing study methods and findings

## Obtaining All dbGaP Studies

### Approaches Evaluated

| Approach                         | Result                | Issue                                               |
| -------------------------------- | --------------------- | --------------------------------------------------- |
| **dbGaP FHIR API**               | Partial success       | Returns study metadata but limited variable details |
| **dbGaP FTP**                    | Success for variables | `var_report.xml` files available per study          |
| **Programmatic Advanced Search** | Failed                | No documented API; CSV export is session-based      |
| **Web scraping**                 | Not attempted         | Fragile, potentially against ToS                    |

### Final Approach: Manual Export + FTP

The most reliable method combines:

1. **Study list**: Manual CSV export from [dbGaP Advanced Search](https://www.ncbi.nlm.nih.gov/gap/advanced_search/) → "Save CSV" button
2. **Variable data**: Automated download from dbGaP FTP (`var_report.xml` files)
3. **Harmonization data**: Clone TOPMed GitHub repo + download phenotype tags CSV

### Study Metadata Fields (from Advanced Search CSV)

| Field           | Description                    |
| --------------- | ------------------------------ |
| Study Accession | phs###### identifier           |
| Study Name      | Full study title               |
| Description     | Study abstract/summary         |
| Disease/Focus   | Primary condition studied      |
| Participants    | Subject count                  |
| Platform        | Sequencing/genotyping platform |
| Release Date    | When data became available     |
| Embargo Date    | When data becomes public       |

## Data Sources

### Priority 1: Available for Download

| Source                           | Records                            | Content                                  | Access                                                                     |
| -------------------------------- | ---------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------- |
| **dbGaP FTP var_report.xml**     | ~340K unique variables             | Variable names, descriptions, statistics | FTP download                                                               |
| **TOPMed Harmonized Phenotypes** | 78 harmonized variables            | dbGaP phv IDs → UMLS CUI mappings        | [GitHub](https://github.com/UW-GAC/topmed-dcc-harmonized-phenotypes)       |
| **TOPMed Phenotype Tags**        | 65 concepts, 16K+ tagged variables | Concept → UMLS CUI mappings              | [CSV download](https://topmed.nhlbi.nih.gov/dcc-phenotype-tagging-details) |

### Priority 2: API/Query Access

| Source             | Records               | Content                               | Access                |
| ------------------ | --------------------- | ------------------------------------- | --------------------- |
| **dbGaP FHIR API** | All studies           | Third-party annotations (LOINC, UMLS) | REST API              |
| **ATHENA/OMOP**    | Standard vocabularies | Concept relationships, synonyms       | Download with license |

### Priority 3: Web-Only / Registration Required

| Source                   | Records                           | Content                       | Access                                           |
| ------------------------ | --------------------------------- | ----------------------------- | ------------------------------------------------ |
| **PhenX-dbGaP Mappings** | 13,653 variables from 521 studies | PhenX ID ↔ dbGaP phv mappings | [Web tool](https://www.phenxtoolkit.org/vsearch) |
| **PheKB**                | ~100 phenotype algorithms         | ICD, RxNorm, LOINC code lists | [Registration](https://phekb.org)                |

## Data Model

### Concept Record

```json
{
  "concept_id": "C0005823",
  "concept_source": "UMLS",
  "preferred_term": "Blood Pressure",
  "definition": "The pressure of the blood within the arteries...",
  "semantic_type": "Laboratory or Test Result",
  "synonyms": ["BP", "arterial pressure", "blood pressure measurement"],
  "related_codes": [
    { "source": "LOINC", "code": "85354-9", "display": "Blood pressure panel" },
    { "source": "SNOMED", "code": "75367002", "display": "Blood pressure" }
  ],
  "dbgap_variables": [
    {
      "phv_id": "phv00054118",
      "pht_id": "pht000001",
      "phs_id": "phs000001",
      "variable_name": "SBP",
      "description": "Systolic blood pressure at baseline",
      "mapping_source": "TOPMed",
      "mapping_confidence": "harmonized"
    }
  ]
}
```

### Variable Record

```json
{
  "phv_id": "phv00054118.v1",
  "pht_id": "pht000001.v2",
  "phs_id": "phs000001.v3",
  "study_name": "NEI Age-Related Eye Disease Study (AREDS)",
  "variable_name": "SBP",
  "description": "SYSTOLIC BLOOD PRESSURE AT BASELINE",
  "data_type": "integer",
  "unit": "mmHg",
  "subject_count": 3762,
  "mapped_concepts": [
    {
      "concept_id": "C2039694",
      "concept_source": "UMLS",
      "mapping_source": "TOPMed",
      "mapping_confidence": "harmonized"
    }
  ]
}
```

## Mapping Confidence Levels

| Level               | Description                                    | Sources                          |
| ------------------- | ---------------------------------------------- | -------------------------------- |
| **harmonized**      | Expert-curated, reproducible mapping with code | TOPMed harmonized phenotypes     |
| **tagged**          | Manual annotation by domain experts            | TOPMed tagging, PhenX comparable |
| **related**         | Similar but may need transformation            | PhenX related mappings           |
| **inferred-high**   | Embedding similarity ≥0.85 to anchor           | Phase 5 propagation              |
| **inferred-medium** | Embedding similarity 0.70–0.84 to anchor       | Phase 5 propagation              |
| **inferred-low**    | Embedding similarity 0.60–0.69 to anchor       | Phase 5 propagation              |

**Note**: Inferred mappings prioritize recall (finding all potentially related variables) over precision. They are suitable for discovery/findability but should be reviewed before use in formal analysis.

## Data Pipeline

### Phase 1: Ingest dbGaP Variables

1. Download var_report.xml for all studies from FTP
2. Parse XML to extract: phv_id, pht_id, phs_id, variable_name, description, data_type, unit, statistics
3. Index in OpenSearch with full-text search on name + description

**Estimated records**: ~340,000 unique variables from 2,721 studies

### Phase 2: Ingest TOPMed Mappings

1. Parse TOPMed harmonized phenotypes JSON files
2. Extract: harmonized variable → component dbGaP phv IDs → UMLS CUI
3. Create concept records with UMLS CUI as concept_id
4. Link dbGaP variables to concepts with confidence="harmonized"

**Estimated records**: 78 concepts, ~500 variable mappings

### Phase 3: Ingest TOPMed Tags

1. Parse TOPMed phenotype tags CSV
2. Create/enrich concept records for 65 phenotype concepts
3. Query dbGaP FHIR API for variables tagged with each UMLS CUI
4. Link variables to concepts with confidence="tagged"

**Estimated records**: 65 concepts, ~16,000 variable mappings

### Phase 4: Enrich with PhenX (Manual/Scraping)

1. For each PhenX variable in toolkit, search vsearch tool
2. Extract linked dbGaP phv IDs
3. Create concept records with PhenX ID
4. Link variables with confidence="tagged" or "related"

**Estimated records**: ~500 PhenX concepts, ~13,653 variable mappings

### Phase 5: Embedding-Based Concept Inference

The existing harmonization efforts (TOPMed, PhenX) cover only ~1.5% of dbGaP variables. Phase 5 uses embedding similarity to extend coverage to the remaining ~98%.

#### Approach: Anchor-Based Propagation

Use expert-curated mappings from Phases 2-4 as "anchors" and propagate their concepts to similar unmapped variables.

```
1. Parse var_report.xml → extract variable names + descriptions
2. Generate embeddings for all variables using embedding model
3. Generate embeddings for anchor variables (those with known UMLS mappings)
4. For each unmapped variable:
   - Compute cosine similarity to all anchors
   - Find best matching anchor(s)
   - Assign anchor's concept with confidence based on similarity score
5. Index in OpenSearch with confidence as filterable field
```

#### Embedding Model Options

| Model                             | Cost                 | Domain     | Notes                                   |
| --------------------------------- | -------------------- | ---------- | --------------------------------------- |
| `text-embedding-3-small` (OpenAI) | ~$0.50 for 340K vars | General    | Good baseline, cheap                    |
| `text-embedding-3-large` (OpenAI) | ~$2.50 for 340K vars | General    | Better quality                          |
| `PubMedBERT`                      | Free                 | Biomedical | May handle medical abbreviations better |
| `all-MiniLM-L6-v2`                | Free                 | General    | Fast, good for prototyping              |

**Recommendation**: Start with `text-embedding-3-small` (<$1) for initial implementation. If precision is insufficient, test biomedical models on a sample.

#### Confidence Thresholds

| Similarity Score | Confidence Label | UI Treatment            |
| ---------------- | ---------------- | ----------------------- |
| ≥0.85            | **high**         | Show prominently        |
| 0.70–0.84        | **medium**       | Show with indicator     |
| 0.60–0.69        | **low**          | Show with caution label |
| <0.60            | —                | Do not surface          |

These thresholds prioritize **recall over precision** since the use case is discovery/findability, not clinical decision-making. Users can filter by confidence level.

#### Cost Estimate

| Item                                        | Cost                    |
| ------------------------------------------- | ----------------------- |
| Embeddings (340K variables × 50 tokens avg) | $0.50–$3                |
| OpenSearch storage                          | Existing infrastructure |
| Compute (cosine similarity)                 | Minimal                 |
| **Total**                                   | **<$10**                |

#### Evaluation Strategy

Before full deployment, validate on a held-out sample:

1. Take 1,000 variables with known TOPMed mappings
2. Remove their mappings, treat as "unmapped"
3. Run anchor propagation
4. Measure: What % are correctly mapped? At what confidence threshold?

This provides empirical thresholds and expected precision/recall.

## Terminology Standards

### Primary Standard: UMLS CUI

UMLS (Unified Medical Language System) is the recommended primary standard because:

- **Already used by TOPMed** anchors (our ground truth)
- **Integrates 190+ source vocabularies** including SNOMED, LOINC, MeSH, HPO
- **3.49 million concepts** with cross-mappings
- **dbGaP's own annotations** use UMLS CUIs

### Secondary Standards (Cross-Referenced)

| Standard      | Size             | Best For                 | When to Use                    |
| ------------- | ---------------- | ------------------------ | ------------------------------ |
| **LOINC**     | ~100K codes      | Lab tests, observations  | Variables measuring lab values |
| **SNOMED CT** | ~350K concepts   | Clinical terminology     | Disease/condition variables    |
| **HPO**       | ~17K terms       | Phenotypic abnormalities | Rare disease phenotypes        |
| **MeSH**      | ~30K descriptors | Literature indexing      | Linking to PubMed              |

Where available, store cross-references to these systems in the `related_codes` field.

## OpenSearch Index Design

### Index: `concepts`

```json
{
  "mappings": {
    "properties": {
      "concept_id": { "type": "keyword" },
      "concept_source": { "type": "keyword" },
      "preferred_term": {
        "type": "text",
        "analyzer": "standard",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "definition": { "type": "text" },
      "semantic_type": { "type": "keyword" },
      "synonyms": { "type": "text", "analyzer": "standard" },
      "related_codes": { "type": "nested" },
      "variable_count": { "type": "integer" }
    }
  }
}
```

### Index: `variables`

```json
{
  "mappings": {
    "properties": {
      "phv_id": { "type": "keyword" },
      "pht_id": { "type": "keyword" },
      "phs_id": { "type": "keyword" },
      "study_name": { "type": "text" },
      "variable_name": {
        "type": "text",
        "analyzer": "standard",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "description": { "type": "text", "analyzer": "standard" },
      "data_type": { "type": "keyword" },
      "unit": { "type": "keyword" },
      "subject_count": { "type": "integer" },
      "mapped_concepts": { "type": "nested" }
    }
  }
}
```

## Search Capabilities

### 1. Exact Term Match

```
GET /concepts/_search
{ "query": { "term": { "preferred_term.keyword": "Blood Pressure" } } }
```

### 2. Synonym Expansion

```
GET /concepts/_search
{ "query": { "multi_match": {
    "query": "BP",
    "fields": ["preferred_term", "synonyms"]
} } }
```

### 3. Fuzzy Matching

```
GET /variables/_search
{ "query": { "match": {
    "description": { "query": "systlic blood presure", "fuzziness": "AUTO" }
} } }
```

### 4. Find Variables by Concept

```
GET /variables/_search
{ "query": { "nested": {
    "path": "mapped_concepts",
    "query": { "term": { "mapped_concepts.concept_id": "C0005823" } }
} } }
```

## Success Metrics

| Metric                        | Target   | Notes                             |
| ----------------------------- | -------- | --------------------------------- |
| Variables indexed             | >300K    | From var_report.xml parsing       |
| Variables with expert mapping | >30,000  | Phases 2-4 (harmonized/tagged)    |
| Variables with any mapping    | >200,000 | Including Phase 5 inferred        |
| Unique concepts               | >500     | UMLS CUIs                         |
| Search latency (p95)          | <200ms   |                                   |
| Recall on held-out test       | >80%     | At inferred-low threshold         |
| Precision at inferred-high    | >70%     | Validated against expert mappings |

## Dependencies

- OpenSearch cluster (existing)
- dbGaP FTP access (public)
- TOPMed GitHub repo (public)
- PhenX web tool (public, may need scraping)

## Timeline

| Phase   | Scope             | Effort                                 |
| ------- | ----------------- | -------------------------------------- |
| Phase 1 | dbGaP variables   | Index ~2M variables                    |
| Phase 2 | TOPMed harmonized | Add 78 concepts, ~500 mappings         |
| Phase 3 | TOPMed tags       | Add 65 concepts, ~16K mappings         |
| Phase 4 | PhenX             | Add ~500 concepts, ~13K mappings       |
| Phase 5 | NLP clustering    | Expand coverage with inferred mappings |

## Study Publications Discovery

### Problem

dbGaP does not maintain a publications database linking papers to studies. This creates two discovery challenges:

1. **Original Research**: Finding the papers that describe the study design, protocols, and primary findings
2. **Secondary Reuse**: Finding papers by other researchers who obtained the data and performed new analyses

**Why this gap exists**: Data Access Requests (DARs) are approved for researchers to use dbGaP data, but there's no requirement to report back publications. NCBI has acknowledged this:

> "Currently, the NCBI provides no direct links to any published research that resulted from specific approved DARs"

### Goal

Enable users to find publications associated with each dbGaP study to understand:

- **Original research**: Study protocols, cohort descriptions, primary findings
- **Secondary analyses**: How others have reused the data, what they discovered
- **Methods context**: How specific variables were collected and used
- **Scientific value**: What claims have been made from this data

### Two Types of Publications

| Type          | Description                                         | Example                                          | Discovery Method               |
| ------------- | --------------------------------------------------- | ------------------------------------------------ | ------------------------------ |
| **Original**  | Papers by study investigators describing the cohort | "The Framingham Heart Study: Design and Methods" | Grant linkage, study documents |
| **Secondary** | Papers by other researchers who reused the data     | "GWAS of blood pressure using FHS data"          | Citation search, DAR tracking  |

### Data Sources for Publication Discovery

| Source                      | Method                       | Best For            | Coverage                   |
| --------------------------- | ---------------------------- | ------------------- | -------------------------- |
| **NIH RePORTER API**        | Grant → Publications linkage | Original papers     | ~60-70% of primary         |
| **PubMed/PMC Full-Text**    | Search "phs######" in text   | Secondary analyses  | Variable (citation habits) |
| **Europe PMC Grant Finder** | Text-mine funding sections   | EU-funded work      | Good for international     |
| **dbGaP Documents Tab**     | Study-submitted references   | Key original papers | Curated but incomplete     |
| **Google Scholar**          | Citation search              | Broad discovery     | Noisy, needs filtering     |

### Publication Discovery Pipeline

#### Phase 1: NIH RePORTER (Original Research)

The most reliable source for finding original study publications.

```
Input: dbGaP Study (phs000007 - Framingham)
                    ↓
Step 1: Query RePORTER for associated grants
        GET https://api.reporter.nih.gov/v2/projects/search
        Filter by: project_terms contains "Framingham" OR
                   project_title contains study name
                    ↓
Step 2: For each grant, retrieve linked publications
        GET https://api.reporter.nih.gov/v2/publications/search
        Filter by: core_project_num = "R01HL12345"
                    ↓
Step 3: Store mappings with metadata
        {
          phs_id: "phs000007",
          pmid: "12345678",
          link_type: "original",
          link_source: "reporter",
          grant_id: "R01HL12345",
          confidence: "high"
        }
```

**Expected yield**: Primary study publications, methods papers, major findings

#### Phase 2: Full-Text Citation Search (Secondary Reuse)

Find papers that cite the dbGaP accession in their text.

```
Input: dbGaP Study accession (phs000007)
                    ↓
Step 1: Search PMC full text
        Query: "phs000007" OR "phs 000007" in body text
        API: E-utilities esearch with [text] field
                    ↓
Step 2: Search PubMed for study name + dbGaP
        Query: "Framingham" AND "dbGaP"
                    ↓
Step 3: Search data availability statements
        Many journals now require these sections
        Query: "data availability" AND "phs000007"
                    ↓
Step 4: Deduplicate against Phase 1 results
        Mark as link_type: "secondary"
```

**Expected yield**: Secondary analyses, replication studies, meta-analyses

**Limitation**: Inconsistent citation practices - many papers don't cite the phs# even when they used the data.

#### Phase 3: Text Mining for Methods & Variables (Future)

Extract detailed information about how data was used.

```
Input: Paper full text (from PMC OA subset)
                    ↓
Step 1: Extract methods section
        Use NLP/LLM to identify Methods/Materials section
                    ↓
Step 2: Identify variable mentions
        "We extracted systolic blood pressure (SBP) and
         diastolic blood pressure (DBP) from baseline exam..."
                    ↓
Step 3: Link to dbGaP variables
        Match mentions to phv IDs using concept mappings
                    ↓
Step 4: Extract protocol details
        "Blood pressure was measured using mercury
         sphygmomanometer after 5 minutes rest..."
                    ↓
Output: {
          pmid: "12345678",
          variables_used: ["phv00000123", "phv00000124"],
          protocol_summary: "BP measured with mercury sphyg...",
          analysis_type: "GWAS"
        }
```

**Expected yield**: Variable-level paper linkages, protocol extraction

**Limitation**: Only works on PMC Open Access papers (~3.4M of ~35M total)

### Coverage Expectations

| Phase        | What It Finds                 | Expected Coverage   | Confidence |
| ------------ | ----------------------------- | ------------------- | ---------- |
| **Phase 1**  | Original study papers         | 60-70% of primary   | High       |
| **Phase 2**  | Papers citing dbGaP accession | 30-50% of secondary | Medium     |
| **Phase 3**  | Variable-level linkages       | Unknown             | Low-Medium |
| **Combined** | Union of all sources          | Best effort         | Varies     |

### The Gap We Cannot Fully Close

**Complete tracking is impossible** because:

- No requirement to report publications from DAR approvals
- Inconsistent citation practices (many don't cite phs#)
- Some papers behind paywalls, not searchable
- International researchers may not use NIH grants

**Our approach is best-effort discovery, not complete tracking.** We should clearly communicate this limitation to users.

### Open Access & Indexability

| PMC Category                | Articles  | License    | Indexable?        |
| --------------------------- | --------- | ---------- | ----------------- |
| Commercial Use (CC-BY, CC0) | ~1.5M+    | Open       | ✅ Full text      |
| Non-Commercial (CC-BY-NC)   | ~1M+      | Restricted | ⚠️ Research only  |
| Other/Copyright             | ~1M+      | Varies     | ❌ Metadata only  |
| **Total OA Subset**         | **~3.4M** | Mixed      | Check per-article |

**NIH Public Access Policy (2025)**: As of July 2025, all NIH-funded papers must be in PMC immediately upon publication. Since dbGaP studies are NIH-funded, most related papers will be accessible.

### Bulk Download for Indexing

```
FTP: ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/
  ├── oa_comm/xml/    # Commercial use OK - safe to index
  ├── oa_noncomm/xml/ # Non-commercial only
  └── oa_other/xml/   # Check individually

AWS S3: s3://pmc-oa-opendata (free egress)
```

### Publication Record Schema

```json
{
  "pmid": "12345678",
  "pmcid": "PMC1234567",
  "title": "Genome-wide association study of...",
  "journal": "Nature Genetics",
  "year": 2023,
  "authors": ["Smith J", "Jones M"],
  "abstract": "...",
  "linked_studies": [
    {
      "phs_id": "phs000007",
      "link_source": "reporter",
      "grant_id": "R01HL123456"
    }
  ],
  "full_text_available": true,
  "license": "CC-BY-4.0",
  "methods_extracted": false
}
```

### Open Questions - Publications

1. **Scope**: Index all PMC OA papers, or only those linked to dbGaP studies?
2. **Methods Extraction**: Use LLM to extract protocols from methods sections?
3. **Variable-Paper Linking**: Can we automatically detect which variables a paper used?

## Platform Deep Links (Study Detail Page)

The study detail page currently shows a "View in AnVIL" link for AnVIL-hosted studies (see `buildViewInAnVIL` in `viewModelBuilders.ts`). This section documents how to add equivalent deep links for the remaining three NCPI platforms.

### Current State

| Platform  | Deep link?                                                        | Status                                                                    |
| --------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **AnVIL** | `https://explore.anvilproject.org/datasets?filter=<encoded_json>` | Implemented — filters by `datasets.registered_identifier` using `dbGapId` |
| **BDC**   | Not yet                                                           | Planned                                                                   |
| **CRDC**  | Not yet                                                           | Planned                                                                   |
| **KFDRC** | Not yet                                                           | Blocked (see below)                                                       |

### BDC (BioData Catalyst) — No per-study deep link

**URL pattern:** `https://gen3.biodatacatalyst.nhlbi.nih.gov/discovery`

- The Gen3 Discovery frontend does not support a `keyword` query parameter — the URL simply opens the discovery page where users can search manually.
- Individual study detail pages (`/discovery/<guid>/`) use GUIDs with version+consent group suffixes (e.g., `phs000179.v6.p2.c1`) that don't match the `studyAccession` stored in our catalog (e.g., `phs000179.v6.p2`), so per-study deep links are not feasible.
- **261 BDC studies** in catalog.

### CRDC (GDC Portal) — Medium

**URL pattern:** `https://portal.gdc.cancer.gov/projects/${gdcProjectId}`

- GDC uses project IDs (e.g., `TARGET-AML`, `CPTAC-3`), not phs IDs, in URLs.
- The GDC API provides a phs→projectId mapping at `https://api.gdc.cancer.gov/projects?fields=project_id,dbgap_accession_number&size=100`. All 47 CRDC studies in the catalog have matching GDC project IDs (100% coverage verified Feb 2026).
- **Implementation:** Fetch the mapping at catalog build time and store a `gdcProjectId` field in the catalog data.
- **47 CRDC studies** in catalog.

### KFDRC (Kids First) — Blocked

**Portal URL:** `https://portal.kidsfirstdrc.org/`

- The Kids First portal requires login for all study pages (uses `ProtectedRoute`).
- Studies are identified by internal `SD_*` codes (e.g., `SD_BHJXBDQK`) in portal routes (`/data-exploration/:studyCode`), not phs IDs.
- The FHIR API (`kf-api-fhir-service.kidsfirstdrc.org`) used to refresh KFDRC source data is **dead** (ECONNREFUSED as of Feb 2026). The source file (`catalog-build/source/kfdrc-studies.json`) does not exist.
- The FHIR response never contained `SD_*` codes — only numeric IDs and phs accessions. So even when the refresh worked, it could not provide the mapping needed for deep links.
- The `kf-api-dataservice.kidsfirstdrc.org` API also appears unreachable.

**Best available options for KFDRC:**

1. Link to `https://portal.kidsfirstdrc.org/public-studies` (no login required, but no per-study deep link)
2. Link to `https://portal.kidsfirstdrc.org/studies` (requires login, no per-study deep link)
3. Obtain `SD_*` → phs mapping from the Kids First team and link to `/data-exploration/<SD_CODE>` (requires login)
4. Monitor `https://data.kidsfirstdrc.org` (newer catalog portal, URL structure unknown)

### Implementation Plan

1. Add `buildViewInBDC()` view builder using the keyword search URL pattern
2. Add GDC project ID fetch to the catalog build pipeline; add `buildViewInCRDC()` view builder
3. Add a generic KFDRC portal link (option 1 or 2 above) until a better path is available
4. Add conditional `ConditionalComponent` entries to `overviewSideColumn.ts` for each new platform, matching the existing AnVIL pattern

### KFDRC Data Refresh — Broken

The KFDRC data refresh pipeline is independently broken and should be tracked separately:

- The FHIR endpoint is offline
- No source JSON file exists
- The 37 KFDRC studies currently in the catalog are stale and cannot be updated
- Possible fix: use the Kids First Arranger GraphQL API (if accessible) or coordinate with the KF team for a data dump

## Open Questions

1. **PhenX Data Access**: Should we contact RTI International for bulk data access, or implement web scraping?
2. **UMLS License**: Do we need a UMLS license to use CUIs in the concept database? (Likely yes for production use)
3. **Update Frequency**: How often should we refresh from source data?
4. **Concept Hierarchy**: Should we model parent/child concept relationships (e.g., "Systolic BP" is-a "Blood Pressure")?
5. **Embedding Model Selection**: Should we run a formal comparison of biomedical vs general models on a sample before full deployment?
6. **Threshold Tuning**: Are the proposed confidence thresholds (0.60/0.70/0.85) appropriate, or should they be empirically determined?

## Decisions Made

1. **Primary standard**: UMLS CUI (integrates other standards, already used by TOPMed)
2. **Confidence approach**: Three-tier inferred confidence (high/medium/low) based on embedding similarity
3. **Optimization target**: Recall over precision (better to show more candidates with confidence labels than miss relevant variables)
4. **Budget**: <$10 for embedding generation (340K variables much smaller than initially estimated)

## References

- [TOPMed Phenotype Harmonization Paper](https://academic.oup.com/aje/article/190/10/1977/6228144)
- [PhenX-dbGaP Mapping Paper](https://www.nature.com/articles/s41597-022-01660-4)
- [dbGaP Third-Party Annotations](https://ncbiinsights.ncbi.nlm.nih.gov/2023/07/13/dbgap-third-party-annotations/)
- [TOPMed GitHub](https://github.com/UW-GAC/topmed-dcc-harmonized-phenotypes)
- [PhenX Variable Search](https://www.phenxtoolkit.org/vsearch)
- [PheKB](https://phekb.org/)
- [UMLS 2025AB Statistics](https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/statistics.html)
- [HPO-SNOMED Interoperability Study](https://pmc.ncbi.nlm.nih.gov/articles/PMC4748471/)
- [NIH RePORTER API](https://api.reporter.nih.gov/)
- [PMC Open Access Subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/)
- [Europe PMC Grant Finder](https://europepmc.org/grantfinder)
- [dbGaP Citation Guidelines](https://www.ncbi.nlm.nih.gov/books/NBK570249/)

## Appendix: Data Already Downloaded

As of January 2025, the following source data has been downloaded:

| Source                       | Location                                                               | Size   | Records                         |
| ---------------------------- | ---------------------------------------------------------------------- | ------ | ------------------------------- |
| dbGaP var_report.xml         | `catalog-build/source/dbgap-variables/`                                | 642 MB | 14,416 files from 2,721 studies |
| TOPMed harmonized phenotypes | `catalog-build/source/harmonization-sources/topmed-harmonized/`        | ~1 MB  | 78 JSON files                   |
| TOPMed phenotype tags        | `catalog-build/source/harmonization-sources/topmed-phenotype-tags.csv` | 57 KB  | 65 concepts                     |

### dbGaP Variable Statistics

| Metric                     | Value               |
| -------------------------- | ------------------- |
| Studies with variable data | 2,721               |
| Total unique variables     | 340,617             |
| Min variables per study    | 2                   |
| Max variables per study    | 57,042 (Framingham) |
| Mean per study             | 125                 |
| Median per study           | 15                  |

**Distribution:**

- 66% of studies have 11-50 variables
- Only 60 studies (2%) have >1,000 variables
- Top studies: Framingham (57K), WHI (6.3K), FHS (4.8K)
