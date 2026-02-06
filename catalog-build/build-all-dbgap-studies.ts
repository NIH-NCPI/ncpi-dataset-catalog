/**
 * Builds all dbGaP studies catalog using FTP + Gap DB + SRA data sources.
 * Replaces FHIR-based builder with direct NCBI sources for complete coverage.
 */

import { parseContentRows, readFile } from "../app/utils/tsvParser";
import {
  NCPIStudy,
  PLATFORM,
  PlatformStudy,
} from "../app/apis/catalog/ncpi-catalog/common/entities";
import { generateConsentDescriptions } from "./common/consent-codes";
import {
  combineDataTypes,
  fetchAllStudyIds,
  fetchFTPStudyData,
  fetchGapStudyData,
  fetchSRADataTypes,
  getDbGapUrl,
} from "./common/dbgap-ftp";
import {
  DUOS_INFO_SOURCE_FIELD_KEY,
  DUOS_INFO_SOURCE_FIELD_TYPE,
  duosCsvPath,
  SOURCE_FIELD_KEY,
  SOURCE_FIELD_TYPE,
  tsvPath,
} from "./constants";
import { DuosStudyInfo } from "./entities";

// Rate limiting delay between API calls (ms)
const API_DELAY = 350;

// Progress logging interval
const PROGRESS_INTERVAL = 50;

/**
 * Delays execution for rate limiting.
 * @param ms
 */
async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Loads platform assignments from TSV file.
 * @returns Map of dbGapId to array of platforms.
 */
async function loadPlatformAssignments(): Promise<Map<string, PLATFORM[]>> {
  const file = await readFile(tsvPath);
  if (!file) {
    console.warn(`Platform TSV not found at ${tsvPath}, using empty map`);
    return new Map();
  }

  const platformStudies = (await parseContentRows(
    file,
    "\t",
    SOURCE_FIELD_KEY,
    SOURCE_FIELD_TYPE
  )) as PlatformStudy[];

  const platformMap = new Map<string, PLATFORM[]>();
  for (const study of platformStudies) {
    const existing = platformMap.get(study.dbGapId) || [];
    if (!existing.includes(study.platform)) {
      existing.push(study.platform);
    }
    platformMap.set(study.dbGapId, existing);
  }

  return platformMap;
}

/**
 * Loads DUOS URLs from CSV file.
 * @returns Map of dbGapId to DUOS URL.
 */
async function loadDuosUrls(): Promise<Map<string, string>> {
  const file = await readFile(duosCsvPath);
  if (!file) {
    console.warn(`DUOS CSV not found at ${duosCsvPath}, using empty map`);
    return new Map();
  }

  const duosInfo = (await parseContentRows(
    file,
    ",",
    DUOS_INFO_SOURCE_FIELD_KEY,
    DUOS_INFO_SOURCE_FIELD_TYPE
  )) as DuosStudyInfo[];

  return new Map(
    duosInfo.map((info) => [info["Study PHS"], info["Study URL"]])
  );
}

/**
 * Checks if a study has required fields for inclusion.
 * Platform studies (from TSV) are always included if they have a title.
 * Non-platform studies require both title and participant count.
 * @param title - Study title.
 * @param participantCount - Number of participants.
 * @param isPlatformStudy - Whether this study is in the platform TSV.
 */
function isStudyComplete(
  title: string | undefined,
  participantCount: number | null,
  isPlatformStudy: boolean
): boolean {
  if (!title) return false;
  // Platform studies are included even without participant count
  if (isPlatformStudy) return true;
  // Non-platform studies need participant count
  return !!(participantCount && participantCount > 0);
}

/**
 * Builds all dbGaP studies from FTP + Gap DB + SRA sources.
 * @returns Array of NCPIStudy objects.
 */
export async function buildAllDbGapStudies(): Promise<NCPIStudy[]> {
  console.log("Loading platform assignments...");
  const platformMap = await loadPlatformAssignments();
  console.log(`  Loaded ${platformMap.size} platform-assigned studies`);

  console.log("Loading DUOS URLs...");
  const duosUrlMap = await loadDuosUrls();
  console.log(`  Loaded ${duosUrlMap.size} DUOS URLs`);

  console.log("Fetching all study IDs from FTP...");
  const allStudyIds = await fetchAllStudyIds();
  console.log(`  Found ${allStudyIds.length} studies on FTP`);

  const studies: NCPIStudy[] = [];
  let skippedIncomplete = 0;
  let skippedNoFtp = 0;
  let processed = 0;

  console.log("Processing studies...");

  for (const phsId of allStudyIds) {
    processed++;

    if (processed % PROGRESS_INTERVAL === 0) {
      console.log(
        `  Progress: ${processed}/${allStudyIds.length} (${studies.length} valid, ${skippedIncomplete} incomplete, ${skippedNoFtp} no FTP data)`
      );
    }

    // Fetch FTP data (GapExchange XML) — may be null for child studies
    const ftpData = await fetchFTPStudyData(phsId);

    await delay(API_DELAY);

    // Fetch Gap DB data
    const gapData = await fetchGapStudyData(phsId);

    // Resolve title: prefer FTP, fall back to esummary
    const title = ftpData?.title || gapData.studyName;
    if (!title) {
      skippedNoFtp++;
      continue;
    }

    // Check if this is a platform study (from TSV)
    const isPlatformStudy = platformMap.has(phsId);

    // Get participant count from Gap DB
    const participantCount = gapData.participantCount;

    // Check completeness - platform studies included even without participant count
    if (!isStudyComplete(title, participantCount, isPlatformStudy)) {
      skippedIncomplete++;
      continue;
    }

    await delay(API_DELAY);

    // Fetch SRA data types if Gap DB doesn't have any
    let sraDataTypes: string[] = [];
    if (gapData.dataTypes.length === 0) {
      sraDataTypes = await fetchSRADataTypes(phsId);
      await delay(API_DELAY);
    }

    // Combine data types with fallback logic
    const dataTypes = combineDataTypes(
      gapData.dataTypes,
      sraDataTypes,
      gapData.genotypePlatforms
    );

    // Consent codes come from FTP only; empty for child studies without FTP
    const consentCodes = ftpData?.consentCodes || [];
    const consentLongNames: Record<string, string> = {};
    for (const code of consentCodes) {
      const descriptions = await generateConsentDescriptions(code);
      consentLongNames[code] = descriptions.consentLongName;
    }

    // Resolve accession: prefer FTP, fall back to esummary
    const studyAccession = ftpData?.studyAccession || gapData.studyAccession || phsId;

    // Determine platforms - use platform map or default to [PLATFORM.DBGAP]
    const platforms = platformMap.get(phsId) || [PLATFORM.DBGAP];

    // Build the study object
    const study: NCPIStudy = {
      consentCodes,
      consentLongNames,
      dataTypes,
      dbGapId: phsId,
      dbGapUrl: getDbGapUrl(studyAccession),
      description: ftpData?.description || "",
      duosUrl: duosUrlMap.get(phsId) ?? null,
      focus: gapData.diseases[0] || "",
      numChildren: gapData.numChildren,
      parentStudyId: gapData.parentStudyId,
      parentStudyName: gapData.parentStudyName,
      participantCount: participantCount || 0,
      platforms,
      studyAccession,
      studyDesigns: ftpData?.studyTypes || gapData.studyTypes,
      title,
    };

    studies.push(study);
  }

  console.log(`\nBuild complete:`);
  console.log(`  Total processed: ${processed}`);
  console.log(`  Valid studies: ${studies.length}`);
  console.log(`  Skipped (incomplete): ${skippedIncomplete}`);
  console.log(`  Skipped (no FTP data): ${skippedNoFtp}`);

  return studies;
}

/**
 * Builds studies for a subset of IDs (for testing).
 * @param phsIds - Array of phs IDs to build.
 * @returns Array of NCPIStudy objects.
 */
export async function buildStudiesForIds(
  phsIds: string[]
): Promise<NCPIStudy[]> {
  console.log("Loading platform assignments...");
  const platformMap = await loadPlatformAssignments();

  console.log("Loading DUOS URLs...");
  const duosUrlMap = await loadDuosUrls();

  const studies: NCPIStudy[] = [];

  for (const phsId of phsIds) {
    console.log(`Processing ${phsId}...`);

    // Fetch FTP data — may be null for child studies
    const ftpData = await fetchFTPStudyData(phsId);

    await delay(API_DELAY);

    const gapData = await fetchGapStudyData(phsId);

    // Resolve title: prefer FTP, fall back to esummary
    const title = ftpData?.title || gapData.studyName;
    if (!title) {
      console.log(`  Skipped: No title from FTP or esummary`);
      continue;
    }

    // Check if this is a platform study (from TSV)
    const isPlatformStudy = platformMap.has(phsId);

    // Get participant count from Gap DB
    const participantCount = gapData.participantCount;

    if (!isStudyComplete(title, participantCount, isPlatformStudy)) {
      console.log(
        `  Skipped: Incomplete (title: ${!!title}, participants: ${participantCount}, platform: ${isPlatformStudy})`
      );
      continue;
    }

    await delay(API_DELAY);

    let sraDataTypes: string[] = [];
    if (gapData.dataTypes.length === 0) {
      sraDataTypes = await fetchSRADataTypes(phsId);
      await delay(API_DELAY);
    }

    const dataTypes = combineDataTypes(
      gapData.dataTypes,
      sraDataTypes,
      gapData.genotypePlatforms
    );

    const consentCodes = ftpData?.consentCodes || [];
    const consentLongNames: Record<string, string> = {};
    for (const code of consentCodes) {
      const descriptions = await generateConsentDescriptions(code);
      consentLongNames[code] = descriptions.consentLongName;
    }

    const studyAccession = ftpData?.studyAccession || gapData.studyAccession || phsId;
    const platforms = platformMap.get(phsId) || [PLATFORM.DBGAP];

    const study: NCPIStudy = {
      consentCodes,
      consentLongNames,
      dataTypes,
      dbGapId: phsId,
      dbGapUrl: getDbGapUrl(studyAccession),
      description: ftpData?.description || "",
      duosUrl: duosUrlMap.get(phsId) ?? null,
      focus: gapData.diseases[0] || "",
      numChildren: gapData.numChildren,
      parentStudyId: gapData.parentStudyId,
      parentStudyName: gapData.parentStudyName,
      participantCount: participantCount || 0,
      platforms,
      studyAccession,
      studyDesigns: ftpData?.studyTypes || gapData.studyTypes,
      title,
    };

    studies.push(study);
    console.log(
      `  Added: ${study.title} (${participantCount || 0} participants)`
    );
  }

  return studies;
}
