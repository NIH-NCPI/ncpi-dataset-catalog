/**
 * FHIR-first builder for all dbGaP studies.
 * Fetches all studies from FHIR API and applies platform assignments.
 */

import { parseContentRows, readFile } from "../app/utils/tsvParser";
import {
  NCPIStudy,
  PLATFORM,
  PlatformStudy,
} from "../app/apis/catalog/ncpi-catalog/common/entities";
import { generateConsentDescriptions } from "./common/consent-codes";
import {
  fetchAllFHIRStudies,
  FHIRStudyData,
  getDbGapUrl,
} from "./common/dbgap-fhir";
import {
  fetchFTPStudyData,
  fetchGapStudyData,
  getDbGapUrl as getFTPDbGapUrl,
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
 * @returns Map of study PHS to DUOS URL.
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
 * Generates consent long names for an array of consent codes.
 * @param consentCodes - Array of consent code strings.
 * @returns Record mapping codes to long names.
 */
async function buildConsentLongNames(
  consentCodes: string[]
): Promise<Record<string, string>> {
  const consentLongNames: Record<string, string> = {};
  for (const code of consentCodes) {
    const descriptions = await generateConsentDescriptions(code);
    consentLongNames[code] = descriptions.consentLongName;
  }
  return consentLongNames;
}

/**
 * Converts FHIR study data to NCPIStudy format.
 * @param fhirStudy - FHIR study data.
 * @param platformMap - Map of dbGapId to platforms.
 * @param duosUrlMap - Map of dbGapId to DUOS URL.
 * @returns NCPIStudy object.
 */
async function convertToNCPIStudy(
  fhirStudy: FHIRStudyData,
  platformMap: Map<string, PLATFORM[]>,
  duosUrlMap: Map<string, string>
): Promise<NCPIStudy> {
  const consentLongNames = await buildConsentLongNames(fhirStudy.consentCodes);
  const platforms = platformMap.get(fhirStudy.dbGapId) || [PLATFORM.DBGAP];

  return {
    consentCodes: fhirStudy.consentCodes,
    consentLongNames,
    dataTypes: fhirStudy.dataTypes,
    dbGapId: fhirStudy.dbGapId,
    dbGapUrl: getDbGapUrl(fhirStudy.studyAccession),
    description: fhirStudy.description,
    duosUrl: duosUrlMap.get(fhirStudy.dbGapId) ?? null,
    focus: fhirStudy.focus,
    participantCount: fhirStudy.participantCount,
    platforms,
    studyAccession: fhirStudy.studyAccession,
    studyDesigns: fhirStudy.studyDesigns,
    title: fhirStudy.title,
  };
}

/**
 * Delay helper for rate limiting.
 * @param ms - Milliseconds to delay.
 * @returns Promise that resolves after delay.
 */
async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Fetches a missing platform study from FTP as fallback.
 * @param phsId - The phs ID to fetch.
 * @param platformMap - Map of dbGapId to platforms.
 * @param duosUrlMap - Map of dbGapId to DUOS URL.
 * @returns NCPIStudy or null if not found.
 */
async function fetchMissingStudyFromFTP(
  phsId: string,
  platformMap: Map<string, PLATFORM[]>,
  duosUrlMap: Map<string, string>
): Promise<NCPIStudy | null> {
  const ftpData = await fetchFTPStudyData(phsId);
  if (!ftpData || !ftpData.title) return null;

  await delay(350);
  const gapData = await fetchGapStudyData(phsId);

  const consentLongNames = await buildConsentLongNames(ftpData.consentCodes);
  const platforms = platformMap.get(phsId) || [PLATFORM.DBGAP];

  return {
    consentCodes: ftpData.consentCodes,
    consentLongNames,
    dataTypes: gapData.dataTypes,
    dbGapId: phsId,
    dbGapUrl: getFTPDbGapUrl(ftpData.studyAccession),
    description: ftpData.description,
    duosUrl: duosUrlMap.get(phsId) ?? null,
    focus: gapData.diseases[0] || "",
    participantCount: gapData.participantCount || 0,
    platforms,
    studyAccession: ftpData.studyAccession,
    studyDesigns: ftpData.studyTypes,
    title: ftpData.title,
  };
}

/**
 * Tracks study statistics during build.
 */
interface BuildStats {
  platformStudiesCount: number;
  withDataTypes: number;
  withParticipants: number;
}

/**
 * Updates build statistics for a study.
 * @param study - The study to track.
 * @param stats - The stats object to update.
 */
function updateStats(study: NCPIStudy, stats: BuildStats): void {
  if (study.participantCount > 0) stats.withParticipants++;
  if (study.dataTypes.length > 0) stats.withDataTypes++;
  if (study.platforms.some((p) => p !== PLATFORM.DBGAP)) {
    stats.platformStudiesCount++;
  }
}

/**
 * Converts FHIR studies to NCPI format.
 * @param fhirStudies - Array of FHIR studies.
 * @param platformMap - Map of dbGapId to platforms.
 * @param duosUrlMap - Map of dbGapId to DUOS URL.
 * @param stats - Stats object to update.
 * @returns Array of NCPIStudy objects.
 */
async function convertFHIRStudies(
  fhirStudies: FHIRStudyData[],
  platformMap: Map<string, PLATFORM[]>,
  duosUrlMap: Map<string, string>,
  stats: BuildStats
): Promise<NCPIStudy[]> {
  console.log("Converting to NCPIStudy format...");
  const studies: NCPIStudy[] = [];

  for (let i = 0; i < fhirStudies.length; i++) {
    const study = await convertToNCPIStudy(
      fhirStudies[i],
      platformMap,
      duosUrlMap
    );
    studies.push(study);
    updateStats(study, stats);

    if ((i + 1) % 500 === 0) {
      console.log(`  Converted: ${i + 1}/${fhirStudies.length}`);
    }
  }

  return studies;
}

/**
 * Recovers missing platform studies from FTP.
 * @param missingIds - Array of missing phs IDs.
 * @param platformMap - Map of dbGapId to platforms.
 * @param duosUrlMap - Map of dbGapId to DUOS URL.
 * @param stats - Stats object to update.
 * @returns Array of recovered NCPIStudy objects.
 */
async function recoverMissingStudies(
  missingIds: string[],
  platformMap: Map<string, PLATFORM[]>,
  duosUrlMap: Map<string, string>,
  stats: BuildStats
): Promise<NCPIStudy[]> {
  console.log(
    `\nFetching ${missingIds.length} missing platform studies from FTP...`
  );
  const recovered: NCPIStudy[] = [];

  for (const phsId of missingIds) {
    const study = await fetchMissingStudyFromFTP(
      phsId,
      platformMap,
      duosUrlMap
    );
    if (study) {
      recovered.push(study);
      updateStats(study, stats);
      console.log(`  Recovered: ${phsId} - ${study.title.slice(0, 50)}...`);
    } else {
      console.log(`  Not found: ${phsId}`);
    }
    await delay(350);
  }

  console.log(`  Recovered ${recovered.length} of ${missingIds.length}`);
  return recovered;
}

/**
 * Builds all dbGaP studies from FHIR API.
 * Falls back to FTP for platform studies not in FHIR.
 * @returns Array of all NCPIStudy objects.
 */
export async function buildAllFHIRStudies(): Promise<NCPIStudy[]> {
  console.log("Loading platform assignments...");
  const platformMap = await loadPlatformAssignments();
  console.log(`  Loaded ${platformMap.size} platform-assigned studies`);

  console.log("Loading DUOS URLs...");
  const duosUrlMap = await loadDuosUrls();
  console.log(`  Loaded ${duosUrlMap.size} DUOS URLs`);

  const fhirStudies = await fetchAllFHIRStudies();
  const foundIds = new Set(fhirStudies.map((s) => s.dbGapId));

  const stats: BuildStats = {
    platformStudiesCount: 0,
    withDataTypes: 0,
    withParticipants: 0,
  };

  const studies = await convertFHIRStudies(
    fhirStudies,
    platformMap,
    duosUrlMap,
    stats
  );

  const missingPlatformIds = [...platformMap.keys()].filter(
    (id) => !foundIds.has(id)
  );

  if (missingPlatformIds.length > 0) {
    const recovered = await recoverMissingStudies(
      missingPlatformIds,
      platformMap,
      duosUrlMap,
      stats
    );
    studies.push(...recovered);
  }

  console.log(`\nBuild complete:`);
  console.log(`  Total studies: ${studies.length}`);
  console.log(`  With participant count > 0: ${stats.withParticipants}`);
  console.log(`  With data types: ${stats.withDataTypes}`);
  console.log(`  Platform studies (non-dbGaP): ${stats.platformStudiesCount}`);

  return studies;
}

// Allow running directly
if (require.main === module) {
  buildAllFHIRStudies()
    .then((studies) => {
      console.log(`\nBuilt ${studies.length} studies`);
    })
    .catch(console.error);
}
