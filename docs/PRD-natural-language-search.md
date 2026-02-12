# PRD: Natural Language Search over NIH Genomic Datasets

## Overview

This document defines the requirements for building a comprehensive discovery layer over NIH genomic datasets. The primary data source is dbGaP (database of Genotypes and Phenotypes), which serves as the central registry for controlled-access human genomic studies at NIH. The system will enable researchers to:

1. **Query across all studies** — not just those hosted on specific cloud platforms
2. **Search variables by concept** — finding all variables measuring the same thing regardless of naming conventions
3. **Discover research context** — understanding both the original research that produced the data and secondary analyses that reused it

The concept database will use OpenSearch to provide exact match, synonym lookup, and fuzzy matching on phenotype terms, mapping them to standardized concept codes and clustered variable groups.

## Problem Statement

### Enabling Unified Search Across Studies and Variables

Researchers need to answer questions like:

- _"Which studies focus on cardiovascular disease and have whole genome sequencing data?"_ (disease focus + assay type)
- _"Show me all studies with RNA-seq data related to autism"_ (assay type + disease focus)
- _"Find me studies with WGS data that also collect systolic blood pressure variables"_ (assay type + variable)
- _"What diabetes-related phenotype variables exist across all NIH genomic studies?"_ (variable discovery)

These questions span two levels of search:

1. **Study-level search** by disease focus and molecular data type (assay) — the most common entry point for researchers browsing available datasets
2. **Variable-level search** by phenotype concept — a deeper capability for researchers who need specific measurements across studies

**Today, answering these questions requires navigating multiple systems.** Relevant capabilities exist but are spread across different tools, each covering a subset of studies:

- **dbGaP Advanced Search** supports faceted filtering by disease, data type, and a "Common Data Elements" facet. It covers all dbGaP studies but each platform's studies must be discovered separately.
- **PIC-SURE (BioData Catalyst)** allows keyword-based variable search across BDC-hosted studies, but covers the ~273 studies on that platform.
- **Platform-specific search** on AnVIL, BDC, CRDC, and Kids First each operates on its own subset of studies, with no cross-platform search.

No single interface lets a researcher filter by disease focus and assay type across all NIH genomic datasets, then drill into the phenotype variables available in matching studies.

### Opportunity 1: Unified Study Search by Focus and Assay Type

The four NCPI cloud platforms (AnVIL, BDC, CRDC, KFDRC) collectively host ~412 unique dbGaP studies — roughly **13% of the ~3,100 released studies** in dbGaP. The platforms serve largely non-overlapping research communities with minimal overlap (only 6 studies appear on more than one platform).

The NCPI Dataset Catalog already includes dbGaP itself as a fifth source, bringing study coverage to ~94% (~2,944 studies). With this broad coverage in place, the opportunity is to provide **rich, natural-language search over study-level metadata** — disease focus, molecular data types (WGS, WES, RNA-seq, genotyping arrays, etc.), study design, and participant populations — across all studies in a single interface.

### Opportunity 2: Concept-Based Variable Search

Beyond study-level search, researchers need to find specific phenotype measurements across studies. dbGaP contains an estimated **500,000+ unique phenotype variables** across ~3,100 studies (extrapolated from 384,987 variables across 1,169 studies reported in the [dbgap2x paper, 2018](https://academic.oup.com/bioinformatics/article/36/4/1305/5556117); the database has since grown to 3,100+ studies). Each study uses its own naming conventions:

- "systolic blood pressure" vs "SBP" vs "bp_sys" vs "SYSBP" all mean the same thing
- Concept-based search that resolves synonymous variable names does not yet exist across all studies
- Cross-study analysis requires manual curation of variable mappings

Valuable harmonization and annotation efforts have mapped an estimated **5-8% of variables** to standard concepts:

| Source                           | Variables Mapped                                         | Studies | Type                                  |
| -------------------------------- | -------------------------------------------------------- | ------- | ------------------------------------- |
| **TOPMed Harmonized Phenotypes** | ~1,000-2,000 source variables -> 78 harmonized variables | 17      | Deep harmonization with code          |
| **TOPMed Phenotype Tagging**     | 16,671 tagged variables across 65 concepts               | 17      | Concept tagging (UMLS CUI)            |
| **PhenX-dbGaP Mapping**          | 13,653 variables                                         | 521     | Protocol-level mapping (LOINC, PhenX) |
| **NLM Lister Hill / MDM**        | Unknown count                                            | 585+    | LOINC and UMLS CUI annotations        |

Since 2023, dbGaP's Advanced Search exposes these annotations through a **Common Data Elements (CDE) facet**, making the annotated subset searchable by UMLS, LOINC, and PhenX terms. This project aims to build on these foundations and extend concept mapping coverage to the remaining ~92-95% of variables using embedding-based inference.

### Opportunity 3: Aggregated Research Context

NIH genomic studies generate rich research context — including protocol documents, PI-curated publications, and approved data access requests — but this information is **distributed across multiple systems**, making it time-consuming to synthesize:

- **Protocols**: Large studies like Framingham have 1,000+ protocol documents and questionnaire forms, but these are individual PDFs, not indexed or summarized.
- **Publications**: PI-curated PMIDs appear in GapExchange XML; citing papers can be found in PMC and via NIH RePORTER grant linkage. No single view aggregates all of these.
- **Secondary use**: Approved Data Access Requests with research use statements exist on study pages, but are not indexed. There is no systematic tracking of publications resulting from approved DARs.

The catalog can add value by **aggregating and presenting** these distributed pieces into a coherent research context view for each study.

## Goals

1. **Broad Study Coverage**: Include all ~3,100 dbGaP studies, not just platform-hosted ones
2. **Study Search by Focus and Assay**: Enable filtering and natural-language search by disease focus, molecular data type, study design, and participant population
3. **Variable Concept Search**: Enable searching by variable name, description, or concept term to find related phenotype variables across studies
4. **Synonym Support**: Return matches for synonymous terms (e.g., "BP" -> "blood pressure")
5. **Concept Clustering**: Group variables that measure the same underlying concept, with standard code mappings (UMLS CUI, LOINC)
6. **Publication Discovery**: Surface papers describing study methods and findings

## Study Ingestion

**Status: Implemented**

### Architecture

The catalog ingests all dbGaP studies using two data sources, building on dbGaP's publicly available metadata:

#### 1. dbGaP Advanced Search CSV Export

**Source:** Manual CSV export from [dbGaP Advanced Search](https://www.ncbi.nlm.nih.gov/gap/advanced_search/) -> "Save CSV" button.

Provides for each study:

| Field                     | Description                                        |
| ------------------------- | -------------------------------------------------- |
| Study Accession           | Full accession (e.g., `phs000007.v35.p16`)         |
| Study Name                | Full study title                                   |
| Description               | Truncated study abstract/summary                   |
| Study Disease/Focus       | Primary condition studied                          |
| Study Content             | Participant count, dataset counts, variable counts |
| Study Molecular Data Type | Sequencing/genotyping data types                   |
| Study Design              | Cohort, case-control, etc.                         |
| Study Consent             | Consent codes with descriptions                    |
| Parent study              | Parent study name and accession (for sub-studies)  |

This CSV is the authoritative study list. It is re-exported periodically to capture new studies.

#### 2. FTP GapExchange XML (for Full Descriptions)

**Source:** `https://ftp.ncbi.nlm.nih.gov/dbgap/studies/{phsId}/{version}/GapExchange_{version}.xml`

The CSV description field is truncated. For each study, the build fetches the full description from the GapExchange XML on the dbGaP FTP server. Falls back to the truncated CSV description if the FTP fetch fails.

### Inclusion Criteria

- **Platform studies** (listed in `dashboard-source-ncpi.tsv`): Included if they have a title, even without participant count
- **Non-platform studies**: Require both title AND participant count > 0

This ensures platform studies are never dropped, while filtering out incomplete or placeholder entries.

### Key Files

| File                                      | Purpose                                                   |
| ----------------------------------------- | --------------------------------------------------------- |
| `catalog-build/update-dbgap-source.ts`    | Reads CSV, filters IDs, updates platform study list       |
| `catalog-build/common/dbGapCSVandFTP.ts`  | CSV parsing, FTP description fetching, study construction |
| `catalog-build/build-platform-studies.ts` | Enriches platform studies with dbGaP data                 |
| `catalog-build/build-ncpi-catalog.ts`     | Main orchestrator for full catalog build                  |

## Publications Discovery

### Context

Publication data for NIH genomic studies is available from multiple sources — PI-curated PMIDs in dbGaP's GapExchange XML, grant-linked papers in NIH Reporter, and citing papers in PMC — but no single view aggregates all of these for a given study.

Key challenges:

1. **Original Research**: PI-curated publications exist for some studies in GapExchange XML, but coverage varies across studies.
2. **Secondary Reuse**: Researchers who receive data access can publish analyses, but there is no requirement to report back publications. Many papers don't cite the study accession even when they used the data.

### Goal

Enable users to find publications associated with each study to understand:

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

| Source                    | Method                        | Best For            | Coverage                   |
| ------------------------- | ----------------------------- | ------------------- | -------------------------- |
| **dbGaP GapExchange XML** | PI-curated PMIDs from FTP     | Key original papers | Curated but incomplete     |
| **NIH RePORTER API**      | Grant -> Publications linkage | Original papers     | ~60-70% of primary         |
| **PubMed/PMC Full-Text**  | Search "phs######" in text    | Secondary analyses  | Variable (citation habits) |

### Publication Discovery Pipeline

#### Phase 1: PI-Curated Publications from GapExchange XML — Implemented

For each study, fetch the `<SelectedPublications>` section from the GapExchange XML on the dbGaP FTP server to get PI-curated PMIDs. Batch-resolve PMIDs via the Semantic Scholar API for full metadata (title, authors, DOI, journal, citation counts).

- **Script:** `catalog-build/fetch-dbgap-selected-publications.ts`
- **Output:** `catalog/dbgap-selected-publications.json` (~35 MB)
- **Runtime:** ~30 minutes (rate-limited FTP + S2 API calls for ~3,000 studies)
- **Requires:** `S2_API_KEY` environment variable

#### Phase 2: NIH RePORTER Grant-Linked Publications — Implemented

For each study, search the NIH Reporter API for grants mentioning the study name. Collect core project numbers from matching grants and fetch all publications (PMIDs) linked to those grants. Produces a broader set than PI-curated publications.

- **Script:** `catalog-build/fetch-grant-publications.ts`
- **Output:** `catalog/grant-publications.json` (~227 MB)
- **Runtime:** Several hours (Reporter recommends no more than 1 req/sec)

#### Phase 3: PMC Full-Text Citation Search — Implemented

Search PubMed Central via NCBI eUtils for papers that cite or mention each study's dbGaP accession (e.g., "phs000007") in their text. Fetch metadata (title, authors, journal, year) via eSummary.

- **Script:** `catalog-build/fetch-pmc-citations.ts`
- **Output:** `catalog/pmc-citations.json`
- **Runtime:** Several hours (NCBI rate limit: 3 requests/second)

#### Phase 4: Text Mining for Variable-Level Linkages — Future

Extract detailed information from paper methods sections about which specific variables were used. This would enable linking individual variables to the papers that analyzed them.

- Only works on PMC Open Access papers (~3.4M of ~35M total)
- Requires NLP/LLM to identify methods sections and variable mentions
- Would match mentions to phv IDs using concept mappings from the concept database

### Coverage Expectations

| Phase        | What It Finds                    | Expected Coverage   | Confidence |
| ------------ | -------------------------------- | ------------------- | ---------- |
| **Phase 1**  | PI-curated key papers            | Curated subset      | High       |
| **Phase 2**  | Original study papers via grants | 60-70% of primary   | High       |
| **Phase 3**  | Papers citing study accession    | 30-50% of secondary | Medium     |
| **Phase 4**  | Variable-level linkages          | Unknown             | Low-Medium |
| **Combined** | Union of all sources             | Best effort         | Varies     |

### Publication Record Schema

```json
{
  "pmid": "12345678",
  "pmcid": "PMC1234567",
  "title": "Genome-wide association study of...",
  "journal": "Nature Genetics",
  "year": 2023,
  "authors": ["Smith J", "Jones M"],
  "linked_studies": [
    {
      "phs_id": "phs000007",
      "link_source": "selected_publications | reporter | pmc_citation",
      "grant_id": "R01HL123456"
    }
  ]
}
```

### The Gap We Cannot Fully Close

**Complete publication tracking is inherently difficult** because:

- No requirement to report publications from DAR approvals
- Inconsistent citation practices (many papers don't cite the study accession)
- Some papers behind paywalls, not searchable in PMC
- International researchers may not use NIH grants

**Our approach is best-effort discovery, not complete tracking.** We should clearly communicate this limitation to users.

## Data Sources

### Priority 1: Available for Download

| Source                           | Records                                                         | Content                                  | Access                                                                     |
| -------------------------------- | --------------------------------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------- |
| **dbGaP FTP var_report.xml**     | ~500K+ unique variables (estimated)                             | Variable names, descriptions, statistics | FTP download                                                               |
| **TOPMed Harmonized Phenotypes** | 78 harmonized variables (~1,000-2,000 source variable mappings) | dbGaP phv IDs -> UMLS CUI mappings       | [GitHub](https://github.com/UW-GAC/topmed-dcc-harmonized-phenotypes)       |
| **TOPMed Phenotype Tags**        | 65 concepts, 16,671 tagged variables                            | Concept -> UMLS CUI mappings             | [CSV download](https://topmed.nhlbi.nih.gov/dcc-phenotype-tagging-details) |

### Priority 2: API/Query Access

| Source             | Records               | Content                               | Access                |
| ------------------ | --------------------- | ------------------------------------- | --------------------- |
| **dbGaP FHIR API** | All studies           | Third-party annotations (LOINC, UMLS) | REST API              |
| **ATHENA/OMOP**    | Standard vocabularies | Concept relationships, synonyms       | Download with license |

### Priority 3: Web-Only / Registration Required

| Source                   | Records                           | Content                         | Access                                           |
| ------------------------ | --------------------------------- | ------------------------------- | ------------------------------------------------ |
| **PhenX-dbGaP Mappings** | 13,653 variables from 521 studies | PhenX ID <-> dbGaP phv mappings | [Web tool](https://www.phenxtoolkit.org/vsearch) |
| **PheKB**                | ~100 phenotype algorithms         | ICD, RxNorm, LOINC code lists   | [Registration](https://phekb.org)                |

## Concept Database

### Data Model

#### Concept Record

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

#### Variable Record

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

### Mapping Confidence Levels

| Level               | Description                                    | Sources                          |
| ------------------- | ---------------------------------------------- | -------------------------------- |
| **harmonized**      | Expert-curated, reproducible mapping with code | TOPMed harmonized phenotypes     |
| **tagged**          | Manual annotation by domain experts            | TOPMed tagging, PhenX comparable |
| **related**         | Similar but may need transformation            | PhenX related mappings           |
| **inferred-high**   | Embedding similarity >=0.85 to anchor          | Phase 5 propagation              |
| **inferred-medium** | Embedding similarity 0.70-0.84 to anchor       | Phase 5 propagation              |
| **inferred-low**    | Embedding similarity 0.60-0.69 to anchor       | Phase 5 propagation              |

**Note**: Inferred mappings prioritize recall (finding all potentially related variables) over precision. They are suitable for discovery/findability but should be reviewed before use in formal analysis.

### Data Pipeline

#### Phase 1: Ingest Variables from dbGaP

1. Download var_report.xml for all studies from FTP
2. Parse XML to extract: phv_id, pht_id, phs_id, variable_name, description, data_type, unit, statistics
3. Index in OpenSearch with full-text search on name + description

**Estimated records**: ~500,000+ unique variables from ~3,100 studies (340,617 variables from 2,721 studies already downloaded; see Appendix)

#### Phase 2: Ingest TOPMed Mappings

1. Parse TOPMed harmonized phenotypes JSON files
2. Extract: harmonized variable -> component dbGaP phv IDs -> UMLS CUI
3. Create concept records with UMLS CUI as concept_id
4. Link variables to concepts with confidence="harmonized"

**Estimated records**: 78 concepts, ~1,000-2,000 source variable mappings

#### Phase 3: Ingest TOPMed Tags

1. Parse TOPMed phenotype tags CSV
2. Create/enrich concept records for 65 phenotype concepts
3. Query dbGaP FHIR API for variables tagged with each UMLS CUI
4. Link variables to concepts with confidence="tagged"

**Estimated records**: 65 concepts, ~16,671 variable mappings

#### Phase 4: Enrich with PhenX (Manual/Scraping)

1. For each PhenX variable in toolkit, search vsearch tool
2. Extract linked dbGaP phv IDs
3. Create concept records with PhenX ID
4. Link variables with confidence="tagged" or "related"

**Estimated records**: ~500 PhenX concepts, ~13,653 variable mappings

#### Phase 5: Embedding-Based Concept Inference

The existing harmonization and annotation efforts (TOPMed, PhenX, NLM/MDM) provide a strong foundation covering an estimated 5-8% of variables. Phase 5 uses embedding similarity to extend coverage to the remaining ~92-95%.

##### Approach: Anchor-Based Propagation

Use expert-curated mappings from Phases 2-4 as "anchors" and propagate their concepts to similar unmapped variables.

```
1. Parse var_report.xml -> extract variable names + descriptions
2. Generate embeddings for all variables using embedding model
3. Generate embeddings for anchor variables (those with known UMLS mappings)
4. For each unmapped variable:
   - Compute cosine similarity to all anchors
   - Find best matching anchor(s)
   - Assign anchor's concept with confidence based on similarity score
5. Index in OpenSearch with confidence as filterable field
```

##### Embedding Model Options

| Model                             | Cost                 | Domain     | Notes                                   |
| --------------------------------- | -------------------- | ---------- | --------------------------------------- |
| `text-embedding-3-small` (OpenAI) | ~$0.75 for 500K vars | General    | Good baseline, cheap                    |
| `text-embedding-3-large` (OpenAI) | ~$3.75 for 500K vars | General    | Better quality                          |
| `PubMedBERT`                      | Free                 | Biomedical | May handle medical abbreviations better |
| `all-MiniLM-L6-v2`                | Free                 | General    | Fast, good for prototyping              |

**Recommendation**: Start with `text-embedding-3-small` (<$1) for initial implementation. If precision is insufficient, test biomedical models on a sample.

##### Confidence Thresholds

| Similarity Score | Confidence Label | UI Treatment            |
| ---------------- | ---------------- | ----------------------- |
| >=0.85           | **high**         | Show prominently        |
| 0.70-0.84        | **medium**       | Show with indicator     |
| 0.60-0.69        | **low**          | Show with caution label |
| <0.60            | --               | Do not surface          |

These thresholds prioritize **recall over precision** since the use case is discovery/findability, not clinical decision-making. Users can filter by confidence level.

##### Cost Estimate

| Item                                         | Cost                    |
| -------------------------------------------- | ----------------------- |
| Embeddings (500K+ variables x 50 tokens avg) | $0.75-$4                |
| OpenSearch storage                           | Existing infrastructure |
| Compute (cosine similarity)                  | Minimal                 |
| **Total**                                    | **<$10**                |

##### Evaluation Strategy

Before full deployment, validate on a held-out sample:

1. Take 1,000 variables with known TOPMed mappings
2. Remove their mappings, treat as "unmapped"
3. Run anchor propagation
4. Measure: What % are correctly mapped? At what confidence threshold?

This provides empirical thresholds and expected precision/recall.

### Terminology Standards

#### Primary Standard: UMLS CUI

UMLS (Unified Medical Language System) is the recommended primary standard because:

- **Already used by TOPMed** anchors (our ground truth)
- **Integrates 190+ source vocabularies** including SNOMED, LOINC, MeSH, HPO
- **3.49 million concepts** with cross-mappings
- **Used in dbGaP's own annotations**

#### Secondary Standards (Cross-Referenced)

| Standard      | Size             | Best For                 | When to Use                    |
| ------------- | ---------------- | ------------------------ | ------------------------------ |
| **LOINC**     | ~100K codes      | Lab tests, observations  | Variables measuring lab values |
| **SNOMED CT** | ~350K concepts   | Clinical terminology     | Disease/condition variables    |
| **HPO**       | ~17K terms       | Phenotypic abnormalities | Rare disease phenotypes        |
| **MeSH**      | ~30K descriptors | Literature indexing      | Linking to PubMed              |

Where available, store cross-references to these systems in the `related_codes` field.

### OpenSearch Index Design

#### Index: `concepts`

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

#### Index: `variables`

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

### Search Capabilities

#### 1. Exact Term Match

```
GET /concepts/_search
{ "query": { "term": { "preferred_term.keyword": "Blood Pressure" } } }
```

#### 2. Synonym Expansion

```
GET /concepts/_search
{ "query": { "multi_match": {
    "query": "BP",
    "fields": ["preferred_term", "synonyms"]
} } }
```

#### 3. Fuzzy Matching

```
GET /variables/_search
{ "query": { "match": {
    "description": { "query": "systlic blood presure", "fuzziness": "AUTO" }
} } }
```

#### 4. Find Variables by Concept

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
| Variables indexed             | >400K    | From var_report.xml parsing       |
| Variables with expert mapping | >30,000  | Phases 2-4 (harmonized/tagged)    |
| Variables with any mapping    | >300,000 | Including Phase 5 inferred        |
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

| Phase   | Scope                         | Effort                                 |
| ------- | ----------------------------- | -------------------------------------- |
| Phase 1 | Variable ingestion from dbGaP | Index ~500K+ variables                 |
| Phase 2 | TOPMed harmonized             | Add 78 concepts, ~1,000-2,000 mappings |
| Phase 3 | TOPMed tags                   | Add 65 concepts, ~16K mappings         |
| Phase 4 | PhenX                         | Add ~500 concepts, ~13K mappings       |
| Phase 5 | NLP clustering                | Expand coverage with inferred mappings |

## Open Questions

1. **PhenX Data Access**: Should we contact RTI International for bulk data access, or implement web scraping?
2. **UMLS License**: Do we need a UMLS license to use CUIs in the concept database? (Likely yes for production use)
3. **Update Frequency**: How often should we refresh from source data?
4. **Concept Hierarchy**: Should we model parent/child concept relationships (e.g., "Systolic BP" is-a "Blood Pressure")?
5. **Embedding Model Selection**: Should we run a formal comparison of biomedical vs general models on a sample before full deployment?
6. **Threshold Tuning**: Are the proposed confidence thresholds (0.60/0.70/0.85) appropriate, or should they be empirically determined?
7. **Methods Extraction**: Use LLM to extract protocols from methods sections? (Phase 4 publications)
8. **Variable-Paper Linking**: Can we automatically detect which variables a paper used?

## Decisions Made

1. **Primary standard**: UMLS CUI (integrates other standards, already used by TOPMed)
2. **Confidence approach**: Three-tier inferred confidence (high/medium/low) based on embedding similarity
3. **Optimization target**: Recall over precision (better to show more candidates with confidence labels than miss relevant variables)
4. **Budget**: <$10 for embedding generation (500K+ variables at current API pricing)
5. **Study ingestion**: CSV export from dbGaP Advanced Search + FTP for full descriptions
6. **Publication sources**: Three-phase pipeline (GapExchange XML, NIH Reporter, PMC citations) all implemented

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

### Variable Statistics (from Downloaded Snapshot)

These numbers reflect the downloaded data as of January 2025. dbGaP has since grown to ~3,100 released studies; the total variable count is estimated at 500,000+ (extrapolated from 384,987 variables across 1,169 studies reported in the [dbgap2x paper, 2018](https://academic.oup.com/bioinformatics/article/36/4/1305/5556117)).

| Metric                     | Value (downloaded)  |
| -------------------------- | ------------------- |
| Studies with variable data | 2,721               |
| Total unique variables     | 340,617             |
| Min variables per study    | 2                   |
| Max variables per study    | 57,042 (Framingham) |
| Mean per study             | 125                 |
| Median per study           | 15                  |

**Distribution (downloaded snapshot):**

- 66% of studies have 11-50 variables
- Only 60 studies (2%) have >1,000 variables
- Top studies: Framingham (57K), WHI (6.3K), FHS (4.8K)
