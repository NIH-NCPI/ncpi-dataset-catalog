import { PlatformStudy } from "../app/apis/catalog/ncpi-catalog/common/entities";
import { parseContentRows, readFile } from "../app/utils/tsvParser";
import { writeAsJSON } from "./common/utils";
import { buildNCPICatalogPlatforms } from "./build-plaftorms";
import { buildNCPIPlatformStudies } from "./build-platform-studies";
import {
  DUOS_INFO_SOURCE_FIELD_KEY,
  DUOS_INFO_SOURCE_FIELD_TYPE,
  duosCsvPath,
  SOURCE_FIELD_KEY,
  SOURCE_FIELD_TYPE,
  tsvPath,
} from "./constants";
import { DuosStudyInfo } from "./entities";

console.log("Building NCPI Catalog Data");
export {};

/**
 * Returns the NCPI dashboard studies.
 * @returns void
 */
async function buildCatalog(): Promise<void> {
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

  const ncpiCatalogPlatforms = buildNCPICatalogPlatforms(ncpiPlatformStudies);

  await writeAsJSON(
    "catalog/ncpi-platform-studies.json",
    Object.fromEntries(ncpiPlatformStudies.entries())
  );

  await writeAsJSON(
    "catalog/ncpi-platforms.json",
    Object.fromEntries(ncpiCatalogPlatforms.entries())
  );
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

buildCatalog();
