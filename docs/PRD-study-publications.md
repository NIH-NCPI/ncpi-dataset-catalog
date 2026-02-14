# PRD: Study Publications Discovery

## Problem

dbGaP does not maintain a publications database linking papers to studies. This creates two discovery challenges:

1. **Original Research**: Finding the papers that describe the study design, protocols, and primary findings
2. **Secondary Reuse**: Finding papers by other researchers who obtained the data and performed new analyses

**Why this gap exists**: Data Access Requests (DARs) are approved for researchers to use dbGaP data, but there's no requirement to report back publications. NCBI has acknowledged this:

> "Currently, the NCBI provides no direct links to any published research that resulted from specific approved DARs"

## Goal

Enable users to find publications associated with each dbGaP study to understand:

- **Original research**: Study protocols, cohort descriptions, primary findings
- **Secondary analyses**: How others have reused the data, what they discovered
- **Methods context**: How specific variables were collected and used
- **Scientific value**: What claims have been made from this data

## Two Types of Publications

| Type          | Description                                         | Example                                          | Discovery Method               |
| ------------- | --------------------------------------------------- | ------------------------------------------------ | ------------------------------ |
| **Original**  | Papers by study investigators describing the cohort | "The Framingham Heart Study: Design and Methods" | Grant linkage, study documents |
| **Secondary** | Papers by other researchers who reused the data     | "GWAS of blood pressure using FHS data"          | Citation search, DAR tracking  |

## Data Sources for Publication Discovery

| Source                      | Method                       | Best For            | Coverage                   |
| --------------------------- | ---------------------------- | ------------------- | -------------------------- |
| **NIH RePORTER API**        | Grant → Publications linkage | Original papers     | ~60-70% of primary         |
| **PubMed/PMC Full-Text**    | Search "phs######" in text   | Secondary analyses  | Variable (citation habits) |
| **Europe PMC Grant Finder** | Text-mine funding sections   | EU-funded work      | Good for international     |
| **dbGaP Documents Tab**     | Study-submitted references   | Key original papers | Curated but incomplete     |
| **Google Scholar**          | Citation search              | Broad discovery     | Noisy, needs filtering     |

## Publication Discovery Pipeline

### Phase 1: NIH RePORTER (Original Research)

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

### Phase 2: Full-Text Citation Search (Secondary Reuse)

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

### Phase 3: Text Mining for Methods & Variables (Future)

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

## Coverage Expectations

| Phase        | What It Finds                 | Expected Coverage   | Confidence |
| ------------ | ----------------------------- | ------------------- | ---------- |
| **Phase 1**  | Original study papers         | 60-70% of primary   | High       |
| **Phase 2**  | Papers citing dbGaP accession | 30-50% of secondary | Medium     |
| **Phase 3**  | Variable-level linkages       | Unknown             | Low-Medium |
| **Combined** | Union of all sources          | Best effort         | Varies     |

## The Gap We Cannot Fully Close

**Complete tracking is impossible** because:

- No requirement to report publications from DAR approvals
- Inconsistent citation practices (many don't cite phs#)
- Some papers behind paywalls, not searchable
- International researchers may not use NIH grants

**Our approach is best-effort discovery, not complete tracking.** We should clearly communicate this limitation to users.

## Open Access & Indexability

| PMC Category                | Articles  | License    | Indexable?        |
| --------------------------- | --------- | ---------- | ----------------- |
| Commercial Use (CC-BY, CC0) | ~1.5M+    | Open       | ✅ Full text      |
| Non-Commercial (CC-BY-NC)   | ~1M+      | Restricted | ⚠️ Research only  |
| Other/Copyright             | ~1M+      | Varies     | ❌ Metadata only  |
| **Total OA Subset**         | **~3.4M** | Mixed      | Check per-article |

**NIH Public Access Policy (2025)**: As of July 2025, all NIH-funded papers must be in PMC immediately upon publication. Since dbGaP studies are NIH-funded, most related papers will be accessible.

## Bulk Download for Indexing

```
FTP: ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/
  ├── oa_comm/xml/    # Commercial use OK - safe to index
  ├── oa_noncomm/xml/ # Non-commercial only
  └── oa_other/xml/   # Check individually

AWS S3: s3://pmc-oa-opendata (free egress)
```

## Publication Record Schema

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

## Open Questions

1. **Scope**: Index all PMC OA papers, or only those linked to dbGaP studies?
2. **Methods Extraction**: Use LLM to extract protocols from methods sections?
3. **Variable-Paper Linking**: Can we automatically detect which variables a paper used?

## References

- [NIH RePORTER API](https://api.reporter.nih.gov/)
- [PMC Open Access Subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/)
- [Europe PMC Grant Finder](https://europepmc.org/grantfinder)
- [dbGaP Citation Guidelines](https://www.ncbi.nlm.nih.gov/books/NBK570249/)
