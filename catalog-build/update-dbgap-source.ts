import fs from "fs";
import { parse } from "csv-parse/sync";
import {
  DbGapId,
  PLATFORM,
} from "../app/apis/catalog/ncpi-catalog/common/entities";
import { dbgapCsvPath, Platform } from "./constants";
import { DbGapCSVRow } from "./entities";
import {
  getPlatformStudiesStudyIds,
  sourcePath,
  updatePlatformStudiesAndReportNewStudies,
} from "./utils";

function extractBasePhsId(accession: string): DbGapId | null {
  const match = /^phs\d+/.exec(accession);
  return match ? match[0] : null;
}

async function getDbGapIdsFromCsv(csvPath: string): Promise<DbGapId[]> {
  const content = fs.readFileSync(csvPath, "utf-8");
  const records = parse(content, {
    columns: true,
    skip_empty_lines: true,
  }) as DbGapCSVRow[];

  const ids = new Set<DbGapId>();
  for (const row of records) {
    const baseId = extractBasePhsId(row.accession);
    if (baseId) {
      ids.add(baseId);
    }
  }
  return Array.from(ids);
}

async function updateDbGapSource(sourcePath: string): Promise<void> {
  // Get existing platform studies and dbGaP study ids from the NCPI source tsv.
  const [allPlatformStudies, dbgapStudyIds] = await getPlatformStudiesStudyIds(
    sourcePath,
    Platform.DBGAP
  );

  // Get IDs from other platforms (not dbGaP).
  const otherStudyIds = new Set(
    allPlatformStudies
      .filter((platformStudy) => platformStudy.platform !== PLATFORM.DBGAP)
      .map((study) => study.dbGapId)
  );

  // Get all dbGaP IDs from CSV.
  const csvIds = await getDbGapIdsFromCsv(dbgapCsvPath);

  // Filter out IDs that already exist in other platforms.
  const filteredCsvIds = csvIds.filter((id) => !otherStudyIds.has(id));

  // Update platform studies and report new studies for the specified platform.
  updatePlatformStudiesAndReportNewStudies(
    Platform.DBGAP,
    allPlatformStudies,
    filteredCsvIds,
    dbgapStudyIds,
    sourcePath
  );
}

updateDbGapSource(sourcePath);
