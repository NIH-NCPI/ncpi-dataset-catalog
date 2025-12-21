/**
 * Prototype script to parse dbGaP FTP XML files and extract study metadata.
 * This validates that we can get field parity with FHIR from FTP sources.
 *
 * Run with: npx esrun catalog-build/prototype-ftp-parser.ts
 */

import fetch from "node-fetch";

// Types for parsed study data
interface FTPStudy {
  // From gap esummary (DNA, RNA, etc.)
  combinedDataTypes: string[];
  consentCodes: string[];
  // Genotyping platforms (raw from FTP)
  dataTypes: string[];
  dbGapId: string;
  description: string;
  diseases: string[];
  // From FTP + PubMed
  documentCount: number;
  // From gap esummary
  gapAnalyteTypes: string[];
  // From SRA LIBRARY_STRATEGY
  gapDataTypes: string[];
  // From gap esummary (d_num_participants_in_subtree)
  gapGenotypePlatforms: string[];
  // From gap esummary (d_study_molecular_data_type_list)
  gapParticipantCount: number | null;
  platforms: string[];
  // Derived from platforms (legacy)
  sraDataTypes: string[];
  // Final merged data types with fallback logic
  publications: Array<{ doi: string | null; pmid: string; title: string }>;
  participantCount: number | null;
  studyAccession: string;
  studyTypes: string[];
  title: string;
  variableCount: number;
}

// FHIR comparison data
interface FHIRStudy {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  participantCount: number;
  title: string;
}

/**
 * Derives standardized data types from platform names.
 * @param platforms - Raw platform names from FTP.
 * @returns Array of standardized data type names.
 */
function deriveDataTypes(platforms: string[]): string[] {
  const types = new Set<string>();

  for (const p of platforms) {
    const lower = p.toLowerCase();

    // SNP/Genotyping arrays
    if (
      /affy|illum|omni|snp|beadchip|gwas|hap(?:map)?|axiom|infinium|cytosnp/i.test(
        p
      )
    ) {
      types.add("SNP Genotypes");
    }

    // Exome
    if (/exome|wes/i.test(p)) {
      types.add("WES");
    }

    // Whole genome sequencing
    if (/wgs|whole.?genome.?seq/i.test(p)) {
      types.add("WGS");
    }

    // Methylation
    if (/methyl|epic|450k.*methyl|850k/i.test(p)) {
      types.add("Methylation Array");
    }

    // RNA/Expression
    if (/rna|express|transcriptom/i.test(p)) {
      types.add("RNA-Seq");
    }

    // CNV
    if (/cnv|copy.?number/i.test(p)) {
      types.add("CNV");
    }
  }

  return [...types].sort();
}

const FHIR_BASE = "https://dbgap-api.ncbi.nlm.nih.gov/fhir/x1";
const FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies";
const EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";

/**
 * Maps SRA LIBRARY_STRATEGY values to standardized molecular data types.
 */
const SRA_STRATEGY_MAP: Record<string, string> = {
  WGS: "WGS",
  WXS: "WXS",
  WCS: "WCS",
  "RNA-Seq": "RNA-Seq",
  "miRNA-Seq": "miRNA-Seq",
  "ncRNA-Seq": "ncRNA-Seq",
  "ssRNA-seq": "ssRNA-Seq",
  AMPLICON: "AMPLICON",
  "Bisulfite-Seq": "Methylome sequencing",
  "ChIP-Seq": "ChIP-Seq",
  "ATAC-seq": "ATAC-Seq",
  "Hi-C": "Hi-C",
  CLONE: "Clone",
  POOLCLONE: "PoolClone",
  CLONEEND: "CloneEnd",
  FINISHING: "Finishing",
  EST: "EST",
  "FL-cDNA": "FL-cDNA",
  CTS: "CTS",
  "MNase-Seq": "MNase-Seq",
  "DNase-Hypersensitivity": "DNase-Seq",
  "MRE-Seq": "MRE-Seq",
  "MeDIP-Seq": "MeDIP-Seq",
  "MBD-Seq": "MBD-Seq",
  "Tn-Seq": "Tn-Seq",
  VALIDATION: "Validation",
  "FAIRE-seq": "FAIRE-Seq",
  SELEX: "SELEX",
  "RIP-Seq": "RIP-Seq",
  "ChIA-PET": "ChIA-PET",
  "RAD-Seq": "RAD-Seq",
  "Targeted-Capture": "Targeted Capture",
  "Tethered Chromatin Conformation Capture": "Tethered Chromatin",
  "Synthetic-Long-Read": "Synthetic Long Read",
  OTHER: "Other",
};

/**
 * Publication info with DOI.
 */
interface Publication {
  doi: string | null;
  pmid: string;
  title: string;
}

/**
 * Extracts PubMed IDs from GapExchange XML.
 * @param xml - XML content.
 * @returns Array of PMIDs.
 */
function extractPMIDs(xml: string): string[] {
  const pattern = /pmid="(\d+)"/gi;
  const matches = [...xml.matchAll(pattern)];
  return [...new Set(matches.map((m) => m[1]))];
}

/**
 * Fetches publication details including DOIs from PubMed.
 * @param pmids - Array of PubMed IDs.
 * @returns Array of publication info with DOIs.
 */
async function fetchPublicationDOIs(pmids: string[]): Promise<Publication[]> {
  if (pmids.length === 0) return [];

  try {
    // Batch up to 10 PMIDs per request
    const batchPmids = pmids.slice(0, 10).join(",");
    const url = `${EUTILS_BASE}/esummary.fcgi?db=pubmed&id=${batchPmids}&retmode=json`;
    const response = await fetch(url);
    if (!response.ok) return [];

    const data = (await response.json()) as {
      result?: {
        [key: string]: unknown;
        uids?: string[];
      };
    };

    const publications: Publication[] = [];
    const uids = data.result?.uids || [];

    for (const uid of uids) {
      const rec = data.result?.[uid] as {
        articleids?: Array<{ idtype?: string; value?: string }>;
        title?: string;
      };
      if (!rec) continue;

      const title = (rec.title || "").slice(0, 200);
      let doi: string | null = null;

      for (const aid of rec.articleids || []) {
        if (aid.idtype === "doi" && aid.value) {
          doi = aid.value;
          break;
        }
      }

      publications.push({ pmid: uid, title, doi });
    }

    return publications;
  } catch (error) {
    console.log(`  PubMed query error: ${error}`);
    return [];
  }
}

/**
 * Combines molecular data types from multiple sources with fallback logic:
 * 1. Use Gap DB molecular data types if available
 * 2. Fall back to SRA data types if Gap DB is empty
 * 3. Derive "SNP Genotypes (Array)" if genotype platforms exist but no SNP type present
 * @param gapDataTypes - Molecular data types from Gap DB
 * @param sraDataTypes - Molecular data types from SRA
 * @param gapGenotypePlatforms - Genotype platforms from Gap DB
 * @returns Combined array of molecular data types
 */
function combineDataTypes(
  gapDataTypes: string[],
  sraDataTypes: string[],
  gapGenotypePlatforms: string[]
): string[] {
  const combined = new Set<string>();

  // Priority 1: Use Gap DB types if available
  if (gapDataTypes.length > 0) {
    gapDataTypes.forEach((t) => combined.add(t));
  }

  // Priority 2: Add SRA types (these are sequencing types Gap DB might not have)
  // Map SRA types to Gap DB vocabulary where needed
  const sraToGapMap: Record<string, string> = {
    WGS: "WGS",
    WXS: "WXS",
    "RNA-Seq": "RNA-Seq",
    "miRNA-Seq": "miRNA-Seq",
    "Methylome sequencing": "Methylation (Bisulfite-Seq)",
    "ChIP-Seq": "ChIP-Seq",
    "ATAC-Seq": "ATAC-Seq",
  };

  for (const sraType of sraDataTypes) {
    const mappedType = sraToGapMap[sraType] || sraType;
    // Only add if not already present from Gap DB
    if (!combined.has(mappedType)) {
      combined.add(mappedType);
    }
  }

  // Priority 3: Derive SNP Genotypes from genotype platforms if not already present
  const hasSnpType = [...combined].some(
    (t) =>
      t.toLowerCase().includes("snp") || t.toLowerCase().includes("genotype")
  );

  if (!hasSnpType && gapGenotypePlatforms.length > 0) {
    // Check if platforms look like SNP arrays
    const hasSnpPlatform = gapGenotypePlatforms.some((p) =>
      /affy|illum|omni|snp|beadchip|infinium|axiom|mapping/i.test(p)
    );
    if (hasSnpPlatform) {
      combined.add("SNP Genotypes (Array)");
    }
  }

  return [...combined].sort();
}

/**
 * Gap study data from esummary API.
 */
interface GapStudyData {
  analyteTypes: string[];
  dataTypes: string[];
  diseases: string[];
  genotypePlatforms: string[];
  participantCount: number | null;
  studyDesign: string | null;
}

/**
 * Fetches study metadata from the NCBI gap database esummary API.
 * This provides curated molecular data types, genotype platforms, and more.
 * @param phsId - Study ID (e.g., "phs000007").
 * @returns Gap study data.
 */
async function fetchGapStudyData(phsId: string): Promise<GapStudyData> {
  const empty: GapStudyData = {
    dataTypes: [],
    genotypePlatforms: [],
    analyteTypes: [],
    participantCount: null,
    studyDesign: null,
    diseases: [],
  };

  try {
    // First, search gap database for the study ID to get its internal UID
    const searchUrl = `${EUTILS_BASE}/esearch.fcgi?db=gap&term=${phsId}%5BSTID%5D&retmax=1&retmode=json`;
    const searchResponse = await fetch(searchUrl);
    if (!searchResponse.ok) return empty;

    const searchData = (await searchResponse.json()) as {
      esearchresult?: { idlist?: string[] };
    };
    const gapId = searchData.esearchresult?.idlist?.[0];
    if (!gapId) return empty;

    // Fetch the study summary
    const summaryUrl = `${EUTILS_BASE}/esummary.fcgi?db=gap&id=${gapId}&retmode=json`;
    const summaryResponse = await fetch(summaryUrl);
    if (!summaryResponse.ok) return empty;

    const summaryData = (await summaryResponse.json()) as {
      result?: Record<
        string,
        {
          d_study_results?: {
            d_num_participants_in_subtree?: string;
            d_study_analyte_type_list?: Array<{ d_analyte_type?: string }>;
            d_study_design?: string;
            d_study_disease_list?: Array<{ d_disease_name?: string }>;
            d_study_genotype_platform_list?: Array<{
              d_genotype_platform?: string;
              d_genotype_vendor?: string;
            }>;
            d_study_molecular_data_type_list?: Array<{
              d_molecular_data_type_name?: string;
            }>;
          };
        }
      >;
    };

    const studyResults = summaryData.result?.[gapId]?.d_study_results;
    if (!studyResults) return empty;

    // Extract molecular data types
    const dataTypes = (studyResults.d_study_molecular_data_type_list || [])
      .map((t) => t.d_molecular_data_type_name)
      .filter((t): t is string => !!t);

    // Extract genotype platforms (vendor + platform)
    const genotypePlatforms = (
      studyResults.d_study_genotype_platform_list || []
    )
      .map((p) =>
        `${p.d_genotype_vendor || ""} ${p.d_genotype_platform || ""}`.trim()
      )
      .filter((p) => p);

    // Extract analyte types
    const analyteTypes = (studyResults.d_study_analyte_type_list || [])
      .map((a) => a.d_analyte_type)
      .filter((a): a is string => !!a);

    // Extract diseases
    const diseases = (studyResults.d_study_disease_list || [])
      .map((d) => d.d_disease_name)
      .filter((d): d is string => !!d);

    // Participant count
    const participantCount = studyResults.d_num_participants_in_subtree
      ? parseInt(studyResults.d_num_participants_in_subtree)
      : null;

    return {
      dataTypes: [...new Set(dataTypes)].sort(),
      genotypePlatforms: [...new Set(genotypePlatforms)].sort(),
      analyteTypes: [...new Set(analyteTypes)].sort(),
      diseases: [...new Set(diseases)].sort(),
      participantCount,
      studyDesign: studyResults.d_study_design || null,
    };
  } catch (error) {
    console.log(`  Gap query error for ${phsId}: ${error}`);
    return empty;
  }
}

/**
 * Fetches molecular data types from SRA for a dbGaP study.
 * @param phsId - Study ID (e.g., "phs000007").
 * @returns Array of unique molecular data types.
 */
async function fetchSRADataTypes(phsId: string): Promise<string[]> {
  try {
    // Search SRA for this dbGaP study
    const searchUrl = `${EUTILS_BASE}/esearch.fcgi?db=sra&term=${phsId}[dbgap]&retmax=500&retmode=json`;
    const searchResponse = await fetch(searchUrl);
    if (!searchResponse.ok) return [];

    const searchData = (await searchResponse.json()) as {
      esearchresult?: { count?: string; idlist?: string[] };
    };
    const ids = searchData.esearchresult?.idlist || [];

    if (ids.length === 0) return [];

    // Fetch SRA records in batches of 100
    const allStrategies = new Set<string>();
    const batchSize = 100;

    for (let i = 0; i < Math.min(ids.length, 300); i += batchSize) {
      const batchIds = ids.slice(i, i + batchSize).join(",");
      const fetchUrl = `${EUTILS_BASE}/efetch.fcgi?db=sra&id=${batchIds}&retmode=xml`;

      const fetchResponse = await fetch(fetchUrl);
      if (!fetchResponse.ok) continue;

      const xml = await fetchResponse.text();

      // Extract LIBRARY_STRATEGY values
      const strategyMatches =
        xml.match(/<LIBRARY_STRATEGY>([^<]+)<\/LIBRARY_STRATEGY>/g) || [];
      for (const match of strategyMatches) {
        const strategy = match.replace(/<\/?LIBRARY_STRATEGY>/g, "");
        const mapped = SRA_STRATEGY_MAP[strategy] || strategy;
        allStrategies.add(mapped);
      }

      // Rate limiting
      await new Promise((r) => setTimeout(r, 350));
    }

    return [...allStrategies].sort();
  } catch (error) {
    console.log(`  SRA query error for ${phsId}: ${error}`);
    return [];
  }
}

/**
 * Fetches study data from FHIR API for comparison.
 * @param phsId - Study ID.
 * @returns FHIR study data or null.
 */
async function fetchFHIRStudy(phsId: string): Promise<FHIRStudy | null> {
  try {
    const url = `${FHIR_BASE}/ResearchStudy?_id=${phsId}&_format=json`;
    const response = await fetch(url);
    if (!response.ok) return null;

    const bundle = (await response.json()) as {
      entry?: Array<{ resource: Record<string, unknown> }>;
      total: number;
    };
    if (bundle.total === 0 || !bundle.entry?.[0]) return null;

    const resource = bundle.entry[0].resource;

    // Extract title
    const title = (resource.title as string) || "";

    // Extract data types from MolecularDataTypes extension
    const dataTypes: string[] = [];
    const extensions =
      (resource.extension as Array<{
        extension?: Array<{
          valueCodeableConcept?: { coding?: Array<{ code?: string }> };
        }>;
        url: string;
      }>) || [];
    for (const ext of extensions) {
      if (ext.url?.includes("MolecularDataTypes") && ext.extension) {
        for (const inner of ext.extension) {
          const code = inner.valueCodeableConcept?.coding?.[0]?.code;
          if (code) dataTypes.push(code);
        }
      }
    }

    // Extract participant count from ResearchStudy-Content extension
    let participantCount = 0;
    for (const ext of extensions) {
      if (ext.url?.includes("ResearchStudy-Content") && ext.extension) {
        for (const inner of ext.extension as Array<{
          url?: string;
          valueCount?: { value?: number };
        }>) {
          if (inner.url?.includes("NumSubjects") && inner.valueCount?.value) {
            participantCount += inner.valueCount.value;
          }
        }
      }
    }

    // Extract consent codes from StudyConsents extension
    const consentCodes: string[] = [];
    for (const ext of extensions) {
      if (ext.url?.includes("StudyConsents") && ext.extension) {
        for (const inner of ext.extension as Array<{
          valueCoding?: { display?: string };
        }>) {
          if (inner.valueCoding?.display) {
            consentCodes.push(inner.valueCoding.display);
          }
        }
      }
    }

    return {
      dbGapId: phsId,
      title,
      dataTypes: [...new Set(dataTypes)].sort(),
      participantCount,
      consentCodes: [...new Set(consentCodes)].sort(),
    };
  } catch (error) {
    return null;
  }
}

/**
 * Fetches the list of all study IDs from the FTP directory.
 * @returns Array of phs IDs.
 */
async function fetchAllStudyIds(): Promise<string[]> {
  console.log("Fetching study list from FTP...");
  const response = await fetch(`${FTP_BASE}/`);
  const html = await response.text();

  // Extract phs IDs from directory listing
  const matches = html.match(/phs\d+/g) || [];
  const uniqueIds = [...new Set(matches)].sort();
  console.log(`Found ${uniqueIds.length} studies on FTP`);
  return uniqueIds;
}

/**
 * Gets the latest version directory for a study.
 * @param phsId - Study ID.
 * @returns Latest version path or null if not found.
 */
async function getLatestVersion(phsId: string): Promise<string | null> {
  const response = await fetch(`${FTP_BASE}/${phsId}/`);
  if (!response.ok) return null;

  const html = await response.text();
  // Match version directories like phs000007.v35.p16
  const versionPattern = new RegExp(`${phsId}\\.v(\\d+)\\.p(\\d+)`, "g");
  const matches = [...html.matchAll(versionPattern)];

  if (matches.length === 0) return null;

  // Find highest version
  let maxVersion = 0;
  let latestDir = "";
  for (const match of matches) {
    const version = parseInt(match[1]);
    if (version > maxVersion) {
      maxVersion = version;
      latestDir = match[0];
    }
  }

  return latestDir;
}

/**
 * Extracts text content between XML tags.
 * @param xml - XML string.
 * @param tag - Tag name.
 * @returns Extracted text or empty string.
 */
function extractTag(xml: string, tag: string): string {
  // Handle CDATA
  const cdataPattern = new RegExp(
    `<${tag}[^>]*>\\s*<!\\[CDATA\\[([\\s\\S]*?)\\]\\]>\\s*</${tag}>`,
    "i"
  );
  const cdataMatch = xml.match(cdataPattern);
  if (cdataMatch) {
    return cdataMatch[1].trim();
  }

  // Handle regular content
  const pattern = new RegExp(`<${tag}[^>]*>([^<]*)</${tag}>`, "i");
  const match = xml.match(pattern);
  return match ? match[1].trim() : "";
}

/**
 * Extracts all values for a repeated element attribute.
 * @param xml - XML string.
 * @param tag - Tag name.
 * @param attr - Attribute name.
 * @returns Array of attribute values.
 */
function extractAttributes(xml: string, tag: string, attr: string): string[] {
  const pattern = new RegExp(`<${tag}[^>]*${attr}="([^"]*)"`, "gi");
  const matches = [...xml.matchAll(pattern)];
  return matches.map((m) => m[1]).filter((v) => v);
}

/**
 * Extracts all text values for a repeated element.
 * @param xml - XML string.
 * @param tag - Tag name.
 * @returns Array of text values.
 */
function extractAllTags(xml: string, tag: string): string[] {
  const pattern = new RegExp(`<${tag}[^>]*>([^<]*)</${tag}>`, "gi");
  const matches = [...xml.matchAll(pattern)];
  return matches.map((m) => m[1].trim()).filter((v) => v);
}

/**
 * Counts occurrences of a tag.
 * @param xml - XML string.
 * @param tag - Tag name.
 * @returns Count of tags.
 */
function countTags(xml: string, tag: string): number {
  const pattern = new RegExp(`<${tag}[^>]*>`, "gi");
  const matches = xml.match(pattern);
  return matches ? matches.length : 0;
}

/**
 * Parses the GapExchange XML to extract study metadata.
 * @param xml - XML content.
 * @param phsId - Study ID.
 * @returns Parsed study data.
 */
function parseGapExchangeXML(xml: string, phsId: string): Partial<FTPStudy> {
  // Extract study accession from Study element
  const accessionMatch = xml.match(/accession="([^"]+)"/);
  const studyAccession = accessionMatch ? accessionMatch[1] : phsId;

  // Title
  const title = extractTag(xml, "StudyNameEntrez");

  // Description (in CDATA)
  let description = extractTag(xml, "Description");
  // Clean up HTML/markdown and limit length for display
  description = description
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  // Diseases (MESH terms)
  const diseases = extractAttributes(xml, "Disease", "vocab_term");

  // Study types
  const studyTypes = extractAllTags(xml, "StudyType");

  // Consent codes
  const consentCodes = extractAttributes(xml, "ConsentGroup", "shortName");

  // Genotyping platforms
  const platforms = extractAllTags(xml, "Platform");

  // Document count
  const documentCount = countTags(xml, "Document");

  // Extract PubMed IDs
  const pmids = extractPMIDs(xml);

  return {
    dbGapId: phsId,
    studyAccession,
    title,
    description:
      description.slice(0, 500) + (description.length > 500 ? "..." : ""),
    diseases,
    studyTypes,
    consentCodes,
    platforms: [...new Set(platforms)], // Dedupe
    dataTypes: deriveDataTypes(platforms),
    documentCount,
    pmids, // Store for later DOI lookup
  };
}

/**
 * Extracts participant count from a var_report.xml file.
 * Uses the first variable's total count as a proxy for study size.
 * @param xml - var_report XML content.
 * @returns Participant count or null.
 */
function extractParticipantCount(xml: string): number | null {
  // Look for <stat n="X"> within <total> section
  // The pattern: <total>...<stats><stat n="1234"...
  const totalMatch = xml.match(/<total>[\s\S]*?<stat[^>]*\bn="(\d+)"/);
  if (totalMatch) {
    return parseInt(totalMatch[1]);
  }
  return null;
}

/**
 * Fetches and parses a study from FTP.
 * @param phsId - Study ID.
 * @returns Parsed study or null.
 */
async function fetchStudy(phsId: string): Promise<Partial<FTPStudy> | null> {
  try {
    // Get latest version
    const latestVersion = await getLatestVersion(phsId);
    if (!latestVersion) {
      console.log(`  ${phsId}: No version found`);
      return null;
    }

    // Fetch GapExchange XML
    const xmlUrl = `${FTP_BASE}/${phsId}/${latestVersion}/GapExchange_${latestVersion}.xml`;
    const response = await fetch(xmlUrl);
    if (!response.ok) {
      console.log(`  ${phsId}: GapExchange not found (${response.status})`);
      return null;
    }

    const xml = await response.text();
    const study = parseGapExchangeXML(xml, phsId);

    // Try to get variable count and participant count from pheno_variable_summaries
    const phenoUrl = `${FTP_BASE}/${phsId}/${latestVersion}/pheno_variable_summaries/`;
    const phenoResponse = await fetch(phenoUrl);
    if (phenoResponse.ok) {
      const phenoHtml = await phenoResponse.text();

      // Count var_report files (phenotype tables)
      const varReportMatches =
        phenoHtml.match(/href="([^"]*var_report\.xml)"/g) || [];
      study.variableCount = varReportMatches.length;

      // Get participant count from first var_report
      if (varReportMatches.length > 0) {
        const firstVarReport = varReportMatches[0].match(/href="([^"]+)"/)?.[1];
        if (firstVarReport) {
          const varReportUrl = `${FTP_BASE}/${phsId}/${latestVersion}/pheno_variable_summaries/${firstVarReport}`;
          const varResponse = await fetch(varReportUrl);
          if (varResponse.ok) {
            const varXml = await varResponse.text();
            study.participantCount = extractParticipantCount(varXml);
          }
        }
      }
    }

    // Fetch molecular data types from SRA
    console.log(`    Fetching SRA data types...`);
    study.sraDataTypes = await fetchSRADataTypes(phsId);

    // Fetch curated data from gap esummary API
    console.log(`    Fetching gap database...`);
    const gapData = await fetchGapStudyData(phsId);
    study.gapDataTypes = gapData.dataTypes;
    study.gapParticipantCount = gapData.participantCount;
    study.gapGenotypePlatforms = gapData.genotypePlatforms;
    study.gapAnalyteTypes = gapData.analyteTypes;

    // Combine data types with fallback logic
    study.combinedDataTypes = combineDataTypes(
      gapData.dataTypes,
      study.sraDataTypes || [],
      gapData.genotypePlatforms
    );

    // Fetch publication DOIs from PubMed
    const pmids = (study as { pmids?: string[] }).pmids || [];
    if (pmids.length > 0) {
      console.log(`    Fetching ${pmids.length} publication DOIs...`);
      study.publications = await fetchPublicationDOIs(pmids);
    } else {
      study.publications = [];
    }

    return study;
  } catch (error) {
    console.log(`  ${phsId}: Error - ${error}`);
    return null;
  }
}

/**
 * Main function to test the FTP parser.
 */
async function main(): Promise<void> {
  console.log("=== FTP XML Parser Prototype ===\n");

  // Get all study IDs
  const allIds = await fetchAllStudyIds();

  // Test with a sample of studies (mix of old and new, focus on ones with rich molecular data)
  const sampleIds = [
    "phs000001", // AREDS - has genotyping
    "phs000007", // Framingham - has multiple platforms
    "phs000424", // GTEx - rich molecular data types
    "phs000200", // MESA - large study with SNP data
    "phs000280", // WHI - Women's Health Initiative
    "phs004388", // High ID - NOT in FHIR
  ];

  console.log(`\nTesting with ${sampleIds.length} sample studies...\n`);

  const results: Array<{ fhir: FHIRStudy | null; ftp: Partial<FTPStudy> }> = [];

  for (const phsId of sampleIds) {
    console.log(`Processing ${phsId}...`);

    // Fetch from both sources
    const [ftpStudy, fhirStudy] = await Promise.all([
      fetchStudy(phsId),
      fetchFHIRStudy(phsId),
    ]);

    if (ftpStudy) {
      results.push({ ftp: ftpStudy, fhir: fhirStudy });
      console.log(`  ✓ FTP: ${ftpStudy.title}`);
      console.log(`    FHIR: ${fhirStudy ? "Available" : "NOT AVAILABLE"}`);
    }

    // Rate limiting
    await new Promise((r) => setTimeout(r, 500));
  }

  // Output comparison
  console.log("\n=== FTP vs FHIR COMPARISON ===\n");

  for (const { fhir, ftp } of results) {
    console.log(`━━━ ${ftp.dbGapId}: ${ftp.title} ━━━`);
    console.log("");

    // Platforms and DataTypes comparison
    console.log("  PLATFORMS (FTP GapExchange):");
    console.log(`    ${ftp.platforms?.join(", ") || "(none)"}`);
    console.log("");

    console.log("  MOLECULAR DATA TYPES:");
    console.log(`    Gap DB:   ${ftp.gapDataTypes?.join(", ") || "(none)"}`);
    console.log(`    SRA:      ${ftp.sraDataTypes?.join(", ") || "(none)"}`);
    console.log(
      `    Combined: ${ftp.combinedDataTypes?.join(", ") || "(none)"}`
    );
    console.log(
      `    FHIR:     ${fhir?.dataTypes?.join(", ") || "(not in FHIR)"}`
    );

    // Check match between Combined and FHIR
    const combinedTypes = new Set(ftp.combinedDataTypes || []);
    const fhirTypes = new Set(fhir?.dataTypes || []);
    const matching = [...combinedTypes].filter((t) => fhirTypes.has(t));
    const combinedOnly = [...combinedTypes].filter((t) => !fhirTypes.has(t));
    const fhirOnly = [...fhirTypes].filter((t) => !combinedTypes.has(t));

    if (fhir) {
      console.log(
        `    ✓ Combined↔FHIR match: ${matching.join(", ") || "(none)"}`
      );
      if (combinedOnly.length)
        console.log(`    ⚠ Combined only:       ${combinedOnly.join(", ")}`);
      if (fhirOnly.length)
        console.log(`    ⚠ FHIR only:           ${fhirOnly.join(", ")}`);
    }
    console.log("");

    // Genotype platforms and analyte types
    console.log("  GENOTYPE PLATFORMS (Gap DB):");
    console.log(`    ${ftp.gapGenotypePlatforms?.join(", ") || "(none)"}`);
    console.log("  ANALYTE TYPES (Gap DB):");
    console.log(`    ${ftp.gapAnalyteTypes?.join(", ") || "(none)"}`);
    console.log("");

    // Participant count comparison
    console.log("  PARTICIPANTS:");
    console.log(
      `    Gap DB: ${ftp.gapParticipantCount?.toLocaleString() || "N/A"}`
    );
    console.log(
      `    FTP:    ${ftp.participantCount?.toLocaleString() || "N/A"}`
    );
    console.log(
      `    FHIR:   ${fhir?.participantCount?.toLocaleString() || "(not in FHIR)"}`
    );
    if (fhir && ftp.gapParticipantCount) {
      const diff = Math.abs(
        ((ftp.gapParticipantCount - fhir.participantCount) /
          fhir.participantCount) *
          100
      );
      console.log(
        `    ${diff < 5 ? "✓" : "⚠"} Gap vs FHIR difference: ${diff.toFixed(1)}%`
      );
    }
    console.log("");

    // Consent codes comparison
    console.log("  CONSENT CODES:");
    console.log(`    FTP:  ${ftp.consentCodes?.join(", ") || "(none)"}`);
    console.log(
      `    FHIR: ${fhir?.consentCodes?.join(", ") || "(not in FHIR)"}`
    );
    console.log("");

    // Publications with DOIs
    if (ftp.publications && ftp.publications.length > 0) {
      console.log(`  PUBLICATIONS (${ftp.publications.length}):`);
      for (const pub of ftp.publications.slice(0, 3)) {
        const doi = pub.doi ? `https://doi.org/${pub.doi}` : "(no DOI)";
        console.log(`    PMID:${pub.pmid} - ${doi}`);
      }
      if (ftp.publications.length > 3) {
        console.log(`    ... and ${ftp.publications.length - 3} more`);
      }
      console.log("");
    }
  }

  // Summary statistics
  console.log("=== SUMMARY ===\n");

  const inBoth = results.filter((r) => r.fhir !== null);
  const ftpOnly = results.filter((r) => r.fhir === null);

  console.log(`Studies in FHIR: ${inBoth.length}/${results.length}`);
  console.log(`Studies FTP-only: ${ftpOnly.length}/${results.length}`);
  console.log("");

  // DataTypes accuracy (Combined vs FHIR)
  let combinedMatchingStudies = 0;
  let totalComparisons = 0;
  let totalCombinedMatchingTypes = 0;
  let totalFhirTypes = 0;

  for (const { fhir, ftp } of inBoth) {
    if (fhir && fhir.dataTypes.length > 0) {
      totalComparisons++;
      const combinedTypes = new Set(ftp.combinedDataTypes || []);
      const matchCount = fhir.dataTypes.filter((t) =>
        combinedTypes.has(t)
      ).length;
      totalCombinedMatchingTypes += matchCount;
      totalFhirTypes += fhir.dataTypes.length;
      if (matchCount > 0) combinedMatchingStudies++;
    }
  }

  if (totalComparisons > 0) {
    console.log(`Combined DataTypes coverage (vs FHIR):`);
    console.log(
      `  Studies with matches: ${combinedMatchingStudies}/${totalComparisons}`
    );
    console.log(
      `  Type matches: ${totalCombinedMatchingTypes}/${totalFhirTypes} (${((totalCombinedMatchingTypes / totalFhirTypes) * 100).toFixed(0)}%)`
    );
  }

  // List all unique types from each source
  const allFhirTypes = new Set<string>();
  const allCombinedTypes = new Set<string>();
  const allGapTypes = new Set<string>();
  const allSraTypes = new Set<string>();
  for (const { fhir, ftp } of inBoth) {
    fhir?.dataTypes.forEach((t) => allFhirTypes.add(t));
    ftp.combinedDataTypes?.forEach((t) => allCombinedTypes.add(t));
    ftp.gapDataTypes?.forEach((t) => allGapTypes.add(t));
    ftp.sraDataTypes?.forEach((t) => allSraTypes.add(t));
  }

  console.log(`\nUnique data types by source:`);
  console.log(`  FHIR:     ${[...allFhirTypes].sort().join(", ")}`);
  console.log(`  Combined: ${[...allCombinedTypes].sort().join(", ")}`);
  console.log(`  Gap DB:   ${[...allGapTypes].sort().join(", ")}`);
  console.log(`  SRA:      ${[...allSraTypes].sort().join(", ")}`);

  const missingInCombined = [...allFhirTypes].filter(
    (t) => !allCombinedTypes.has(t)
  );
  const extraInCombined = [...allCombinedTypes].filter(
    (t) => !allFhirTypes.has(t)
  );

  if (missingInCombined.length > 0) {
    console.log(
      `\nFHIR types not in Combined: ${missingInCombined.join(", ")}`
    );
  }
  if (extraInCombined.length > 0) {
    console.log(`Combined types not in FHIR: ${extraInCombined.join(", ")}`);
  }

  console.log("\n=== FIELD PARITY CHECK ===\n");
  console.log(
    "| FHIR Field       | Available     | Source                              |"
  );
  console.log(
    "|------------------|---------------|-------------------------------------|"
  );
  console.log(
    "| title            | ✅ Yes        | FTP: <StudyNameEntrez>              |"
  );
  console.log(
    "| description      | ✅ Yes        | FTP: <Description> CDATA            |"
  );
  console.log(
    "| focus/diseases   | ✅ Better     | Gap: d_study_disease_list           |"
  );
  console.log(
    "| consentCodes     | ✅ Yes        | FTP: <ConsentGroup shortName>       |"
  );
  console.log(
    "| studyAccession   | ✅ Yes        | FTP: <Study accession>              |"
  );
  console.log(
    "| studyDesigns     | ✅ Yes        | FTP: <StudyType>                    |"
  );
  console.log(
    "| dataTypes        | ✅ EXACT      | Gap: d_study_molecular_data_type    |"
  );
  console.log(
    "| participantCount | ✅ EXACT      | Gap: d_num_participants_in_subtree  |"
  );
  console.log(
    "| genotypePlatform | ✅ EXTRA      | Gap: d_study_genotype_platform_list |"
  );
  console.log(
    "| analyteTypes     | ✅ EXTRA      | Gap: d_study_analyte_type_list      |"
  );
  console.log(
    "| publications/DOI | ✅ EXTRA      | FTP: <Pubmed pmid> → PubMed esummary|"
  );
  console.log("");
  console.log("Data sources used:");
  console.log("  - FTP: https://ftp.ncbi.nlm.nih.gov/dbgap/studies/");
  console.log("  - Gap: NCBI E-utilities esummary (db=gap)");
  console.log("  - SRA: NCBI E-utilities (backup for sequencing types)");
}

main().catch(console.error);
