import fs from "fs";
import { parse } from "csv-parse/sync";
import { DbGapId } from "../app/apis/catalog/ncpi-catalog/common/entities";
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
  // Get existing platform studies and study ids from the NCPI source tsv.
  const [platformStudies, studyIds] = await getPlatformStudiesStudyIds(
    sourcePath,
    Platform.DBGAP
  );

  // Get all dbGaP IDs from CSV.
  const csvIds = await getDbGapIdsFromCsv(dbgapCsvPath);

  // Update platform studies and report new studies for the specified platform.
  updatePlatformStudiesAndReportNewStudies(
    Platform.DBGAP,
    platformStudies,
    csvIds,
    studyIds,
    sourcePath
  );
}

updateDbGapSource(sourcePath);
