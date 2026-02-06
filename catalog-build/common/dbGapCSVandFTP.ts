import { decode } from "html-entities";
import fetch from "node-fetch";
import { DbGapStudy } from "../../app/apis/catalog/common/entities";
import { DbGapCSVRow } from "../entities";
import { markdownToHTML } from "./dbGaP";
import { delayFetch } from "./utils";

// Cache for CSV data: Map from phsId (without version) to CSV row
let csvDataCache: Map<string, DbGapCSVRow> | null = null;

// Cache for studies fetched via CSV+FTP
const csvStudyCache = new Map<string, DbGapStudy>();

// Cache for FTP description lookups
const ftpDescriptionCache = new Map<string, string | null>();

// Track missing FTP studies for reporting (Set prevents duplicates)
const missingFtpStudies = new Set<string>();

// dbGaP FTP server base URL for fetching study descriptions
export const dbgapFtpBaseUrl = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies";

/**
 * Initializes the CSV data cache from the provided rows.
 * @param rows - Array of CSV rows from dbGaP advanced search export.
 */
export function initializeCSVCache(rows: DbGapCSVRow[]): void {
  csvDataCache = new Map();
  for (const row of rows) {
    // Extract base phsId without version (e.g., "phs002999.v5.p1" -> "phs002999")
    const phsId = row.accession.split(".")[0];
    csvDataCache.set(phsId, row);
  }
  console.log(`Initialized CSV cache with ${csvDataCache.size} studies`);
}

/**
 * Returns the list of phsIds that were not found on the FTP server.
 * @returns Array of phsIds missing from FTP.
 */
export function getMissingFtpStudies(): string[] {
  return [...missingFtpStudies];
}

/**
 * Parses the "Parent study" CSV field into parent ID and name.
 * Input format: "Study Name (phsXXXXXX.vN.pM)" or "Not Applicable"
 * @param value - The Parent study string from CSV.
 * @returns Object with parentStudyId and parentStudyName, or nulls.
 */
export function parseParentStudy(value: string): {
  parentStudyId: string | null;
  parentStudyName: string | null;
} {
  if (!value || value === "Not Applicable") {
    return { parentStudyId: null, parentStudyName: null };
  }
  const match = value.match(/^(.+?)\s*\((phs\d+)/);
  if (!match) {
    return { parentStudyId: null, parentStudyName: null };
  }
  return { parentStudyId: match[2], parentStudyName: match[1].trim() };
}

/**
 * Parses consent codes from the CSV format.
 * Input: "HMB-IRB-NPU --- Health/Medical/Biomedical (IRB, NPU), DS-FDO-IRB-NPU --- Disease-Specific (Focused Disease Only, IRB, NPU)"
 * Output: ["HMB-IRB-NPU", "DS-FDO-IRB-NPU"]
 * @param consentString - The raw consent string from the CSV.
 * @returns Array of consent code symbols.
 */
export function parseConsentCodes(consentString: string): string[] {
  if (!consentString || consentString === "Not Provided") {
    return [];
  }
  // Match consent codes (uppercase start, then letters/numbers/hyphens) before " --- "
  // Requires uppercase first char to exclude description words, allows mixed case after (e.g., DS-CROTx)
  return consentString.match(/\b[A-Z][A-Za-z0-9-]*(?=\s+---)/g) ?? [];
}

/**
 * Parses the participant count from the Study Content field.
 * Example: "4 phenotype datasets, 24 variables, 2 molecular datasets, 61182 subjects, 61182 samples"
 * @param studyContent - The Study Content string from CSV.
 * @returns The number of subjects, or 0 if not found.
 */
export function parseParticipantCount(studyContent: string): number {
  if (!studyContent) return 0;
  // Find "N subjects" pattern without regex to avoid false positive lint warning
  const marker = " subjects";
  const idx = studyContent.indexOf(marker);
  if (idx === -1) return 0;

  // Walk backwards from the marker to find the start of the number
  let numStart = idx - 1;
  while (numStart >= 0 && /\d/.test(studyContent[numStart])) {
    numStart--;
  }
  numStart++; // Move back to first digit

  if (numStart >= idx) return 0;
  const numStr = studyContent.substring(numStart, idx);
  return parseInt(numStr, 10) || 0;
}

/**
 * Parses comma-separated values, handling "Not Provided" as empty.
 * @param value - Comma-separated string.
 * @returns Array of values.
 */
export function parseCommaSeparated(value: string): string[] {
  if (!value || value === "Not Provided") {
    return [];
  }
  return value
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

/**
 * Parses data types from comma-separated string, removing duplicates.
 * @param value - Comma-separated data types string.
 * @returns Array of unique data type values.
 */
export function parseDataTypes(value: string): string[] {
  return [...new Set(parseCommaSeparated(value))];
}

/**
 * Parses the study focus/disease field.
 * Returns the value as-is (not split on commas, since focus values may contain commas).
 * @param value - The Study Disease/Focus string from CSV.
 * @returns The focus string, or empty string if not provided.
 */
export function parseFocusDisease(value: string): string {
  if (!value || value === "Not Provided") {
    return "";
  }
  return value;
}

/**
 * Parses the study design field.
 * Returns the value wrapped in an array (single value per study).
 * @param value - The Study Design string from CSV.
 * @returns Array containing the study design, or empty array if not provided.
 */
export function parseStudyDesigns(value: string): string[] {
  if (!value || value === "Not Provided") {
    return [];
  }
  return [value];
}

/**
 * Parses version directories from FTP directory listing HTML.
 * @param html - The HTML content of the FTP directory listing.
 * @param phsId - The study ID to match against.
 * @returns Array of version strings (e.g., ["v1.p1", "v2.p2"]).
 */
export function parseVersionsFromHtml(html: string, phsId: string): string[] {
  const versionPattern = new RegExp(`${phsId}\\.(v\\d+\\.p\\d+)/`, "g");
  const versions: string[] = [];
  let match;
  while ((match = versionPattern.exec(html)) !== null) {
    versions.push(match[1]);
  }
  return versions;
}

/**
 * Sorts version strings to get the latest version first.
 * Versions are in format "vN.pM" where N is version number and M is participant number.
 * @param versions - Array of version strings.
 * @returns Sorted array with latest version first.
 */
export function sortVersions(versions: string[]): string[] {
  return [...versions].sort((a, b) => {
    const aMatch = a.match(/v(\d+)\.p(\d+)/);
    const bMatch = b.match(/v(\d+)\.p(\d+)/);
    if (!aMatch || !bMatch) return 0;
    const aVer = parseInt(aMatch[1]) * 1000 + parseInt(aMatch[2]);
    const bVer = parseInt(bMatch[1]) * 1000 + parseInt(bMatch[2]);
    return bVer - aVer;
  });
}

/**
 * Constructs the URL for the latest version's GapExchange XML file.
 * @param phsId - The study ID (e.g., "phs000220").
 * @param versions - Array of version strings (e.g., ["v1.p1", "v2.p2"]).
 * @returns The XML URL for the latest version, or null if no versions provided.
 */
export function getLatestVersionXmlUrl(
  phsId: string,
  versions: string[]
): string | null {
  if (versions.length === 0) return null;
  const sorted = sortVersions(versions);
  const latest = sorted[0];
  return `${dbgapFtpBaseUrl}/${phsId}/${phsId}.${latest}/GapExchange_${phsId}.${latest}.xml`;
}

/**
 * Extracts the study description from GapExchange XML content.
 * Handles both CDATA-wrapped and plain descriptions.
 * @param xml - The XML content of the GapExchange file.
 * @returns The description text, or null if not found.
 */
export function parseDescriptionFromXml(xml: string): string | null {
  const openTag = "<Description>";
  const closeTag = "</Description>";

  const startIdx = xml.indexOf(openTag);
  if (startIdx === -1) return null;

  const contentStart = startIdx + openTag.length;
  const endIdx = xml.indexOf(closeTag, contentStart);
  if (endIdx === -1) return null;

  let content = xml.slice(contentStart, endIdx).trim();
  if (!content) return null;

  // Handle CDATA wrapper
  if (content.startsWith("<![CDATA[") && content.endsWith("]]>")) {
    content = content.slice(9, -3).trim();
  }

  return content || null;
}

/**
 * Fetches the full study description from the dbGaP FTP server.
 * @param phsId - The study ID (e.g., "phs000220").
 * @returns The full description, or null if not found.
 */
async function fetchDescriptionFromFTP(phsId: string): Promise<string | null> {
  // Check cache first
  if (ftpDescriptionCache.has(phsId)) {
    return ftpDescriptionCache.get(phsId) ?? null;
  }

  try {
    await delayFetch(100); // Rate limit

    // Fetch directory listing to find the latest version
    const dirResponse = await fetch(`${dbgapFtpBaseUrl}/${phsId}/`);
    if (!dirResponse.ok) {
      console.log(`FTP directory not found for ${phsId}`);
      ftpDescriptionCache.set(phsId, null);
      missingFtpStudies.add(phsId);
      return null;
    }

    // Find the latest version of the study
    const dirHtml = await dirResponse.text();
    const versions = parseVersionsFromHtml(dirHtml, phsId);
    const xmlUrl = getLatestVersionXmlUrl(phsId, versions);

    // No versions found for study - report, cache, exit
    if (!xmlUrl) {
      console.log(`No version directories found for ${phsId}`);
      ftpDescriptionCache.set(phsId, null);
      missingFtpStudies.add(phsId);
      return null;
    }

    // Rate limit
    await delayFetch(100);

    // Fetch the XML file for the latest version
    const xmlResponse = await fetch(xmlUrl);

    // No file found - report, cache, exit
    if (!xmlResponse.ok) {
      console.log(`XML file not found at ${xmlUrl}`);
      ftpDescriptionCache.set(phsId, null);
      missingFtpStudies.add(phsId);
      return null;
    }

    // Parse description from XML content
    const xmlContent = await xmlResponse.text();
    const description = parseDescriptionFromXml(xmlContent);

    // Description not found in XML - report, cache, exit
    if (!description) {
      console.log(`Description not found in XML for ${phsId}`);
      ftpDescriptionCache.set(phsId, null);
      return null;
    }

    // Cache and return description
    ftpDescriptionCache.set(phsId, description);
    return description;
  } catch (error) {
    // Network or other error - report, cache, exit
    console.log(`Error fetching FTP description for ${phsId}:`, error);
    ftpDescriptionCache.set(phsId, null);
    missingFtpStudies.add(phsId);
    return null;
  }
}

/**
 * Processes a raw description string into HTML.
 * Cleans up whitespace, converts internal dbGaP links to external links,
 * and converts markdown to HTML.
 * @param description - The raw description text.
 * @returns Processed HTML description.
 */
export function processDescription(description: string): string {
  if (!description) {
    return "";
  }

  // Replace newline+tab sequences and tabs with spaces to avoid unwanted formatting
  // Convert internal dbGaP links to external links
  const cleaned = description
    .replace(/\n\n\t/g, " ")
    .replace(/\t/g, " ")
    .replace(
      /study.cgi\?study_id=|.\/study.cgi\?study_id=/g,
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id="
    );

  return markdownToHTML(cleaned);
}

/**
 * Fetches and processes the study description.
 * Tries FTP first for the full description, falls back to CSV truncated description.
 * @param phsId - The study ID.
 * @param csvDescription - The truncated description from CSV as fallback.
 * @returns Processed HTML description.
 */
async function fetchAndProcessDescription(
  phsId: string,
  csvDescription: string
): Promise<string> {
  // Grab full description from FTP, fall back to truncated CSV description.
  let description = await fetchDescriptionFromFTP(phsId);
  if (!description) {
    description = csvDescription || "";
    console.log(`Using CSV description for ${phsId}`);
  }

  // HTML-ize description string
  return processDescription(description);
}

/**
 * Returns the dbGaP study using CSV data and FTP for full descriptions.
 * @param phsId - The study ID (e.g., "phs000220").
 * @returns The study from CSV data with FTP description, or null if not found.
 */
export async function getStudyFromCSVandFTP(
  phsId: string
): Promise<DbGapStudy | null> {
  // Sanity check initialization
  if (!csvDataCache) {
    throw new Error(
      "CSV cache not initialized. Call initializeCSVCache() first."
    );
  }

  // Sanity check phsId format
  if (!phsId.startsWith("phs")) {
    return null;
  }

  // Check study cache first
  const cached = csvStudyCache.get(phsId);
  if (cached) {
    return cached;
  }

  // Grab corresponding CSV row for phsId
  const csvRow = csvDataCache.get(phsId);
  if (!csvRow) {
    console.log(`Study ${phsId} not found in CSV`);
    return null;
  }

  // Parse consent codes
  const consentCodes = parseConsentCodes(csvRow["Study Consent"]);

  // Parse data types
  const dataTypes = parseDataTypes(csvRow["Study Molecular Data Type"]);

  // Fetch and process full description. Falls back to CSV truncated description
  // if not found on FTP, or FTP fetch fails.
  const description = await fetchAndProcessDescription(
    phsId,
    csvRow.description
  );

  // Extract focus (disease/condition)
  const focus = parseFocusDisease(csvRow["Study Disease/Focus"]);

  // Parse participant count from study content
  const participantCount = parseParticipantCount(csvRow["Study Content"]);

  // Parse study designs (single value wrapped in array)
  const studyDesigns = parseStudyDesigns(csvRow["Study Design"]);

  // Decode HTML entities in title
  const title = decode(csvRow.name || "");

  // Parse parent study relationship
  const { parentStudyId, parentStudyName } = parseParentStudy(
    csvRow["Parent study"]
  );

  const study: DbGapStudy = {
    consentCodes,
    dataTypes,
    dbGapId: phsId,
    description,
    focus,
    numChildren: 0,
    parentStudyId,
    parentStudyName,
    participantCount,
    studyAccession: csvRow.accession,
    studyDesigns,
    title,
  };

  csvStudyCache.set(phsId, study);
  return study;
}
