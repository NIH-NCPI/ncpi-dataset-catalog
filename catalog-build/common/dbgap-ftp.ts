/**
 * Data fetching module for dbGaP studies via FTP, Gap DB, and SRA.
 * Replaces FHIR API with direct NCBI sources for complete study coverage.
 */

import fetch from "node-fetch";

const FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies";
const EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";

// Rate limiting delay between NCBI API calls (ms)
const API_DELAY = 350;

/**
 * Data extracted from FTP GapExchange XML.
 */
export interface FTPStudyData {
  consentCodes: string[];
  description: string;
  genotypingPlatforms: string[];
  studyAccession: string;
  studyTypes: string[];
  title: string;
}

/**
 * Data from Gap DB esummary API.
 */
export interface GapStudyData {
  dataTypes: string[];
  diseases: string[];
  genotypePlatforms: string[];
  participantCount: number | null;
  studyDesign: string | null;
}

/**
 * Maps SRA LIBRARY_STRATEGY values to standardized molecular data types.
 */
const SRA_STRATEGY_MAP: Record<string, string> = {
  WGS: "WGS",
  WXS: "WXS",
  "RNA-Seq": "RNA-Seq",
  "miRNA-Seq": "miRNA-Seq",
  "ncRNA-Seq": "ncRNA-Seq",
  AMPLICON: "AMPLICON",
  "Bisulfite-Seq": "Methylome sequencing",
  "ChIP-Seq": "ChIP-Seq",
  "ATAC-seq": "ATAC-Seq",
  "Targeted-Capture": "Targeted-Capture",
  OTHER: "OTHER",
};

/**
 * Delays execution for rate limiting.
 * @param ms
 */
async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Fetches the list of all study IDs from the FTP directory.
 * @returns Array of phs IDs (e.g., "phs000007").
 */
export async function fetchAllStudyIds(): Promise<string[]> {
  const response = await fetch(`${FTP_BASE}/`);
  if (!response.ok) {
    throw new Error(`Failed to fetch FTP directory: ${response.status}`);
  }

  const html = await response.text();
  const matches = html.match(/phs\d+/g) || [];
  return [...new Set(matches)].sort();
}

/**
 * Gets the latest version directory for a study.
 * @param phsId - Study ID (e.g., "phs000007").
 * @returns Latest version path (e.g., "phs000007.v35.p16") or null.
 */
async function getLatestVersion(phsId: string): Promise<string | null> {
  const response = await fetch(`${FTP_BASE}/${phsId}/`);
  if (!response.ok) return null;

  const html = await response.text();
  const versionPattern = new RegExp(`${phsId}\\.v(\\d+)\\.p(\\d+)`, "g");
  const matches = [...html.matchAll(versionPattern)];

  if (matches.length === 0) return null;

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
 * Extracts text content between XML tags, handling CDATA.
 * @param xml
 * @param tag
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
 * @param xml
 * @param tag
 * @param attr
 */
function extractAttributes(xml: string, tag: string, attr: string): string[] {
  const pattern = new RegExp(`<${tag}[^>]*${attr}="([^"]*)"`, "gi");
  const matches = [...xml.matchAll(pattern)];
  return matches.map((m) => m[1]).filter((v) => v);
}

/**
 * Extracts all text values for a repeated element.
 * @param xml
 * @param tag
 */
function extractAllTags(xml: string, tag: string): string[] {
  const pattern = new RegExp(`<${tag}[^>]*>([^<]*)</${tag}>`, "gi");
  const matches = [...xml.matchAll(pattern)];
  return matches.map((m) => m[1].trim()).filter((v) => v);
}

/**
 * Fetches and parses GapExchange XML from FTP.
 * @param phsId - Study ID.
 * @returns Parsed study data or null if not found.
 */
export async function fetchFTPStudyData(
  phsId: string
): Promise<FTPStudyData | null> {
  try {
    const latestVersion = await getLatestVersion(phsId);
    if (!latestVersion) return null;

    const xmlUrl = `${FTP_BASE}/${phsId}/${latestVersion}/GapExchange_${latestVersion}.xml`;
    const response = await fetch(xmlUrl);
    if (!response.ok) return null;

    const xml = await response.text();

    // Extract study accession
    const accessionMatch = xml.match(/accession="([^"]+)"/);
    const studyAccession = accessionMatch ? accessionMatch[1] : phsId;

    // Title
    const title = extractTag(xml, "StudyNameEntrez");

    // Description - keep HTML for now (will be rendered by UI)
    const description = extractTag(xml, "Description");

    // Study types
    const studyTypes = extractAllTags(xml, "StudyType");

    // Consent codes
    const consentCodes = extractAttributes(xml, "ConsentGroup", "shortName");

    // Genotyping platforms
    const genotypingPlatforms = [...new Set(extractAllTags(xml, "Platform"))];

    return {
      title,
      description,
      studyAccession,
      consentCodes,
      studyTypes,
      genotypingPlatforms,
    };
  } catch {
    return null;
  }
}

/**
 * Fetches study metadata from the NCBI Gap database esummary API.
 * @param phsId - Study ID.
 * @returns Gap study data.
 */
export async function fetchGapStudyData(phsId: string): Promise<GapStudyData> {
  const empty: GapStudyData = {
    participantCount: null,
    dataTypes: [],
    genotypePlatforms: [],
    diseases: [],
    studyDesign: null,
  };

  try {
    // Search gap database for the study ID to get its internal UID
    const searchUrl = `${EUTILS_BASE}/esearch.fcgi?db=gap&term=${phsId}%5BSTID%5D&retmax=1&retmode=json`;
    const searchResponse = await fetch(searchUrl);
    if (!searchResponse.ok) return empty;

    const searchData = (await searchResponse.json()) as {
      esearchresult?: { idlist?: string[] };
    };
    const gapId = searchData.esearchresult?.idlist?.[0];
    if (!gapId) return empty;

    await delay(API_DELAY);

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
            d_study_design?: string;
            d_study_disease_list?: Array<{
              d_disease_importance?: string;
              d_disease_name?: string;
            }>;
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

    // Extract genotype platforms
    const genotypePlatforms = (
      studyResults.d_study_genotype_platform_list || []
    )
      .map((p) =>
        `${p.d_genotype_vendor || ""} ${p.d_genotype_platform || ""}`.trim()
      )
      .filter((p) => p);

    // Extract diseases - prioritize primary, then take first
    const diseaseList = studyResults.d_study_disease_list || [];
    const primaryDisease = diseaseList.find(
      (d) => d.d_disease_importance === "primary"
    );
    const diseases = primaryDisease
      ? [primaryDisease.d_disease_name!]
      : diseaseList
          .map((d) => d.d_disease_name)
          .filter((d): d is string => !!d);

    // Participant count
    const participantCount = studyResults.d_num_participants_in_subtree
      ? parseInt(studyResults.d_num_participants_in_subtree)
      : null;

    return {
      participantCount,
      dataTypes: [...new Set(dataTypes)].sort(),
      genotypePlatforms: [...new Set(genotypePlatforms)].sort(),
      diseases: [...new Set(diseases)],
      studyDesign: studyResults.d_study_design || null,
    };
  } catch {
    return empty;
  }
}

/**
 * Fetches molecular data types from SRA for a dbGaP study.
 * Used as fallback when Gap DB doesn't have data types.
 * @param phsId - Study ID.
 * @returns Array of molecular data types.
 */
export async function fetchSRADataTypes(phsId: string): Promise<string[]> {
  try {
    const searchUrl = `${EUTILS_BASE}/esearch.fcgi?db=sra&term=${phsId}[dbgap]&retmax=200&retmode=json`;
    const searchResponse = await fetch(searchUrl);
    if (!searchResponse.ok) return [];

    const searchData = (await searchResponse.json()) as {
      esearchresult?: { idlist?: string[] };
    };
    const ids = searchData.esearchresult?.idlist || [];
    if (ids.length === 0) return [];

    await delay(API_DELAY);

    // Fetch SRA records (limit to first 100 for performance)
    const batchIds = ids.slice(0, 100).join(",");
    const fetchUrl = `${EUTILS_BASE}/efetch.fcgi?db=sra&id=${batchIds}&retmode=xml`;
    const fetchResponse = await fetch(fetchUrl);
    if (!fetchResponse.ok) return [];

    const xml = await fetchResponse.text();
    const allStrategies = new Set<string>();

    const strategyMatches =
      xml.match(/<LIBRARY_STRATEGY>([^<]+)<\/LIBRARY_STRATEGY>/g) || [];
    for (const match of strategyMatches) {
      const strategy = match.replace(/<\/?LIBRARY_STRATEGY>/g, "");
      const mapped = SRA_STRATEGY_MAP[strategy] || strategy;
      allStrategies.add(mapped);
    }

    return [...allStrategies].sort();
  } catch {
    return [];
  }
}

/**
 * Combines molecular data types from multiple sources with fallback logic:
 * 1. Use Gap DB molecular data types if available
 * 2. Add SRA data types
 * 3. Derive "SNP Genotypes (Array)" if genotype platforms exist but no SNP type
 * @param gapDataTypes
 * @param sraDataTypes
 * @param gapGenotypePlatforms
 */
export function combineDataTypes(
  gapDataTypes: string[],
  sraDataTypes: string[],
  gapGenotypePlatforms: string[]
): string[] {
  const combined = new Set<string>();

  // Priority 1: Use Gap DB types
  gapDataTypes.forEach((t) => combined.add(t));

  // Priority 2: Add SRA types
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
    if (!combined.has(mappedType)) {
      combined.add(mappedType);
    }
  }

  // Priority 3: Derive SNP Genotypes from genotype platforms
  const hasSnpType = [...combined].some(
    (t) =>
      t.toLowerCase().includes("snp") || t.toLowerCase().includes("genotype")
  );

  if (!hasSnpType && gapGenotypePlatforms.length > 0) {
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
 * Generates the dbGaP study page URL.
 * @param studyAccession - Study accession ID.
 * @returns URL to the dbGaP study page.
 */
export function getDbGapUrl(studyAccession: string): string {
  return `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=${studyAccession}`;
}
