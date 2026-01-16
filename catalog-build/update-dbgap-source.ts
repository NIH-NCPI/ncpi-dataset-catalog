import fs from "fs";
import { parse } from "csv-parse/sync";
import {
  DbGapId,
  PLATFORM,
  PlatformStudy,
} from "../app/apis/catalog/ncpi-catalog/common/entities";
import {
  dbgapCsvPath,
  Platform,
  SOURCE_FIELD_KEY,
  SOURCE_FIELD_TYPE,
} from "./constants";
import {
  addNCPIHeader,
  mergeSourceStudies,
  replaceTsv,
  reportStudyResults,
  sourcePath,
} from "./utils";
import { parseContentRows, readFile } from "../app/utils/tsvParser";

interface DbGapCsvRow {
  accession: string;
}

function extractBasePhsId(accession: string): DbGapId | null {
  const match = /^phs\d+/.exec(accession);
  return match ? match[0] : null;
}

async function getDbGapIdsFromCsv(csvPath: string): Promise<DbGapId[]> {
  const content = fs.readFileSync(csvPath, "utf-8");
  const records = parse(content, {
    columns: true,
    skip_empty_lines: true,
  }) as DbGapCsvRow[];

  const ids = new Set<DbGapId>();
  for (const row of records) {
    const baseId = extractBasePhsId(row.accession);
    if (baseId) {
      ids.add(baseId);
    }
  }
  return Array.from(ids);
}

async function getAllExistingStudyIds(
  sourcePath: string
): Promise<Set<string>> {
  const file = await readFile(sourcePath);
  if (!file) {
    throw new Error(`File ${sourcePath} not found`);
  }
  const platformStudies = (await parseContentRows(
    file,
    "\t",
    SOURCE_FIELD_KEY,
    SOURCE_FIELD_TYPE
  )) as PlatformStudy[];
  return new Set(platformStudies.map((study) => study.dbGapId));
}

async function updateDbGapSource(sourcePath: string): Promise<void> {
  // Get all existing study IDs from the TSV (across all platforms).
  const existingIds = await getAllExistingStudyIds(sourcePath);

  // Get dbGaP IDs from CSV.
  const csvIds = await getDbGapIdsFromCsv(dbgapCsvPath);

  // Filter to only IDs not already in the TSV.
  const newIds = csvIds.filter((id) => !existingIds.has(id));

  if (newIds.length === 0) {
    console.log("No new dbGaP studies to add.");
    return;
  }

  // Read existing platform studies.
  const file = await readFile(sourcePath);
  if (!file) {
    throw new Error(`File ${sourcePath} not found`);
  }
  const platformStudies = (await parseContentRows(
    file,
    "\t",
    SOURCE_FIELD_KEY,
    SOURCE_FIELD_TYPE
  )) as PlatformStudy[];

  // Get existing dbGaP platform IDs.
  const existingDbGapIds = platformStudies
    .filter((study) => study.platform === PLATFORM.DBGAP)
    .map((study) => study.dbGapId);

  // Combine existing dbGaP IDs with new IDs.
  const allDbGapIds = [...existingDbGapIds, ...newIds];

  // Update spreadsheet.
  const newPlatformStudies = mergeSourceStudies(
    platformStudies,
    Platform.DBGAP,
    allDbGapIds
  );
  replaceTsv(sourcePath, addNCPIHeader(newPlatformStudies));

  // Report new studies.
  reportStudyResults(newIds);
}

updateDbGapSource(sourcePath);
