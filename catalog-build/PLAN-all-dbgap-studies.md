# Plan: Expand Catalog to Include All dbGaP Studies

## Goal

Expand the NCPI Dataset Catalog from ~200 platform-specific studies to include **all dbGaP studies** (~3,300 active studies). This allows users to discover studies available on dbGaP even if they haven't been onboarded to one of the four NCPI platforms (AnVIL, BDC, CRDC, KFDRC).

Note: The FTP directory contains ~4,400 phs directories, but many are withdrawn, unreleased, or incomplete. The dbGaP search interface shows ~3,255 active studies, which aligns with what our build should produce after filtering.

Studies hosted on NCPI platforms will continue to show their platform badges. Studies only available on dbGaP directly will show a "dbGaP" platform indicator.

## Why Not FHIR?

The original approach used the dbGaP FHIR API (`dbgap-api.ncbi.nlm.nih.gov/fhir/x1`), but it only covers ~3,400 studies. The FTP directory contains ~5,000+ studies. To get complete coverage, we switched to direct NCBI sources.

## Architecture

Three data sources are combined to build each study:

### 1. FTP GapExchange XML

**Source:** `https://ftp.ncbi.nlm.nih.gov/dbgap/studies/{phsId}/{version}/GapExchange_{version}.xml`

Provides:

- Title (`<StudyNameEntrez>`)
- Description (`<Description>` CDATA)
- Study accession (e.g., `phs000007.v35.p16`)
- Consent codes (`<ConsentGroup shortName="...">`)
- Study types/designs (`<StudyType>`)
- Genotyping platforms (`<Platform>`)

### 2. Gap DB esummary API

**Source:** NCBI E-utilities `esummary.fcgi?db=gap`

Provides:

- Participant count (`d_num_participants_in_subtree`) - authoritative source
- Molecular data types (`d_study_molecular_data_type_list`) - curated values
- Genotype platforms (`d_study_genotype_platform_list`)
- Disease focus (`d_study_disease_list`)
- Study design (`d_study_design`)

### 3. SRA (Sequence Read Archive)

**Source:** NCBI E-utilities `esearch/efetch?db=sra`

Provides:

- Molecular data types via `LIBRARY_STRATEGY` - used as **fallback** when Gap DB is empty

### Data Type Merging Logic

1. Use Gap DB molecular data types if available (authoritative)
2. Add SRA data types that aren't already present
3. Derive "SNP Genotypes (Array)" if genotype platforms exist but no SNP type present

## Key Files

| File                         | Purpose                                                     |
| ---------------------------- | ----------------------------------------------------------- |
| `build-all-dbgap-studies.ts` | Main builder - iterates all FTP study IDs, fetches metadata |
| `common/dbgap-ftp.ts`        | Core fetch functions for FTP/Gap DB/SRA                     |
| `prototype-ftp-parser.ts`    | Prototype that validates FHIR field parity                  |
| `test-build-subset.ts`       | Test script for validating with a few studies               |
| `test-fhir-build.ts`         | Test script for FHIR-first approach (superseded)            |

## Inclusion Criteria

- **Platform studies** (listed in `dashboard-source-ncpi.tsv`): Included if they have a title, even without participant count
- **Non-platform studies**: Require both title AND participant count > 0

This ensures platform studies are never dropped, while filtering out incomplete/placeholder dbGaP entries.

## Rate Limiting

NCBI E-utilities requires rate limiting:

- 350ms delay between API calls
- Progress logged every 50 studies
- Full build of ~5,000 studies takes several hours

## Current Status

**Infrastructure:** Complete

- `fetchAllStudyIds()` - lists all ~5,000 study IDs from FTP
- `fetchFTPStudyData()` - parses GapExchange XML
- `fetchGapStudyData()` - fetches from Gap DB esummary
- `fetchSRADataTypes()` - fallback molecular data types
- `combineDataTypes()` - merges data types with fallback logic
- `buildAllDbGapStudies()` - main orchestrator
- `buildStudiesForIds()` - for testing subsets

**Validation:** Prototype tested against FHIR to confirm field parity

**Remaining:**

- [ ] Run full build end-to-end
- [ ] Verify output JSON structure matches existing catalog format
- [ ] Update build scripts to use new builder
- [ ] Test filtering/search with expanded dataset
- [ ] Performance testing with ~3,300 studies in browser
- [ ] Extract phenotype variables from `pheno_variable_summaries/*.var_report.xml` for searchability

## Future: Variable/Phenotype Extraction

Each study has detailed variable metadata in `pheno_variable_summaries/` on FTP. This could enable searches like "find studies that measured blood pressure" or "studies with BMI data".

**Data location:**

```
ftp.ncbi.nlm.nih.gov/dbgap/studies/{phsId}/{version}/pheno_variable_summaries/*.var_report.xml
```

**Potential fields to extract:**

- Variable name and description
- Variable type (categorical, continuous, etc.)
- Value ranges/categories
- Number of observations

**Considerations:**

- Large data volume (thousands of variables per study)
- May need separate index/search strategy
- Could significantly increase build time

## Commands

```bash
# Test with subset of studies
npx esrun catalog-build/test-build-subset.ts

# Run prototype comparison (FTP vs FHIR)
npx esrun catalog-build/prototype-ftp-parser.ts
```

### Full Build

The main builder exports functions but doesn't have a CLI entry point yet. To run a full build, create a script or run directly:

```bash
# Option 1: Use the test-fhir-build.ts pattern (writes to /tmp)
npx esrun catalog-build/test-fhir-build.ts

# Option 2: Add a main() to build-all-dbgap-studies.ts that calls:
#   const studies = await buildAllDbGapStudies();
#   await writeAsJSON("catalog/ncpi-all-studies.json", studies);
```

**Note:** Full build takes several hours due to rate limiting (~3,300 studies × 350ms × multiple API calls per study).
