import fs from "fs";
import { Publication } from "../app/apis/catalog/common/entities";
import { PlatformStudy } from "../app/apis/catalog/ncpi-catalog/common/entities";
import { parseContentRows, readFile } from "../app/utils/tsvParser";
import { writeAsJSON } from "./common/utils";
import { buildNCPICatalogPlatforms } from "./build-plaftorms";
import { buildNCPIPlatformStudies } from "./build-platform-studies";
import {
  getMissingFtpStudies,
  initializeCSVCache,
} from "./common/dbGapCSVandFTP";
import {
  dbgapCsvPath,
  DBGAP_CSV_FIELD_KEY,
  DBGAP_CSV_FIELD_TYPE,
  DUOS_INFO_SOURCE_FIELD_KEY,
  DUOS_INFO_SOURCE_FIELD_TYPE,
  duosCsvPath,
  SOURCE_FIELD_KEY,
  SOURCE_FIELD_TYPE,
  tsvPath,
} from "./constants";
import { DbGapCSVRow, DuosStudyInfo } from "./entities";

console.log("Building NCPI Catalog Data");
export {};

/**
 * Returns the NCPI dashboard studies.
 * @returns void
 */
async function buildCatalog(): Promise<void> {
  // Load the dbGaP advanced search CSV and initialize the cache
  const dbgapCsvRows = await readValuesFile<DbGapCSVRow>(
    dbgapCsvPath,
    ",",
    DBGAP_CSV_FIELD_KEY,
    DBGAP_CSV_FIELD_TYPE
  );
  initializeCSVCache(dbgapCsvRows);

  const platformStudyStubs = await readValuesFile<PlatformStudy>(
    tsvPath,
    "\t",
    SOURCE_FIELD_KEY,
    SOURCE_FIELD_TYPE
  );

  const duosInfo = await readValuesFile<DuosStudyInfo>(
    duosCsvPath,
    ",",
    DUOS_INFO_SOURCE_FIELD_KEY,
    DUOS_INFO_SOURCE_FIELD_TYPE
  );
  const duosUrlByDbGapId = new Map(
    duosInfo.map((studyInfo) => [
      studyInfo["Study PHS"],
      studyInfo["Study URL"],
    ])
  );

  const ncpiPlatformStudies = await buildNCPIPlatformStudies(
    platformStudyStubs,
    duosUrlByDbGapId
  );

  // Merge publications from dbgap-publications.json into studies
  const publicationsByStudy = loadPublicationsByStudy();
  let studiesWithPubs = 0;
  for (const study of ncpiPlatformStudies) {
    const pubs = publicationsByStudy.get(study.dbGapId);
    if (pubs) {
      study.publications = pubs;
      studiesWithPubs++;
    }
  }
  console.log(
    `Attached publications to ${studiesWithPubs} of ${ncpiPlatformStudies.length} studies`
  );

  const ncpiCatalogPlatforms = buildNCPICatalogPlatforms(ncpiPlatformStudies);

  await writeAsJSON(
    "catalog/ncpi-platform-studies.json",
    Object.fromEntries(ncpiPlatformStudies.entries())
  );

  await writeAsJSON(
    "catalog/ncpi-platforms.json",
    Object.fromEntries(ncpiCatalogPlatforms.entries())
  );

  // Report any studies that were not found on the FTP server
  const missingFtpStudies = getMissingFtpStudies();
  if (missingFtpStudies.length > 0) {
    console.log(
      `\nWarning: ${missingFtpStudies.length} studies not found on FTP server (using truncated CSV descriptions):`
    );
    for (const phsId of missingFtpStudies) {
      console.log(`  - ${phsId}`);
    }
  }
}

async function readValuesFile<T>(
  filePath: string,
  separator: string,
  sourceFieldKey: Record<string, string>,
  sourceFieldType: Record<string, string>
): Promise<T[]> {
  const file = await readFile(filePath);
  if (!file) {
    throw new Error(`File ${filePath} not found`);
  }
  return await parseContentRows(
    file,
    separator,
    sourceFieldKey,
    sourceFieldType
  );
}

/**
 * Loads publications from dbgap-publications.json and returns a map from phsId to Publication[].
 * @returns Map from dbGaP study ID to simplified publications array.
 */
function loadPublicationsByStudy(): Map<string, Publication[]> {
  const pubsByStudy = new Map<string, Publication[]>();
  const pubsPath = "catalog/dbgap-publications.json";

  if (!fs.existsSync(pubsPath)) {
    console.log("No dbgap-publications.json found, skipping publications");
    return pubsByStudy;
  }

  const raw = JSON.parse(fs.readFileSync(pubsPath, "utf-8"));
  for (const study of raw.studies) {
    if (!study.publications || study.publications.length === 0) continue;
    const pubs: Publication[] = study.publications.map(
      (p: Record<string, unknown>) => ({
        authors: formatAuthors(
          p.authors as { name: string }[] | undefined
        ),
        citationCount: (p.citationCount as number) ?? 0,
        doi: (p.externalIds as Record<string, string>)?.DOI ?? "",
        journal: (p.journal as { name: string })?.name ?? p.venue ?? "",
        title: (p.title as string) ?? "",
        year: (p.year as number) ?? 0,
      })
    );
    // Sort by citation count descending (most-cited first)
    pubs.sort((a, b) => b.citationCount - a.citationCount);
    pubsByStudy.set(study.phsId, pubs);
  }
  console.log(`Loaded publications for ${pubsByStudy.size} studies`);
  return pubsByStudy;
}

/**
 * Formats an array of author objects into a citation-style author string.
 * @param authors - Array of author objects with name property.
 * @returns Formatted author string (e.g., "Smith J, Jones A, et al.").
 */
function formatAuthors(authors: { name: string }[] | undefined): string {
  if (!authors || authors.length === 0) return "";
  if (authors.length <= 3) {
    return authors.map((a) => a.name).join(", ");
  }
  return `${authors
    .slice(0, 3)
    .map((a) => a.name)
    .join(", ")}, et al.`;
}

buildCatalog();
