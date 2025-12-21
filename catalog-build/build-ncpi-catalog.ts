import { writeAsJSON } from "./common/utils";
import { buildNCPICatalogPlatforms } from "./build-plaftorms";
import { buildAllDbGapStudies } from "./build-all-dbgap-studies";

console.log("Building NCPI Catalog Data (All dbGaP Studies)");
export {};

/**
 * Builds the NCPI catalog with ALL dbGaP studies.
 * Uses FTP + Gap DB + SRA sources instead of FHIR API.
 * @returns void
 */
async function buildCatalog(): Promise<void> {
  // Build all dbGaP studies using new FTP+Gap approach
  const ncpiPlatformStudies = await buildAllDbGapStudies();

  // Convert to map for JSON output (keyed by index for backwards compatibility)
  const studiesMap = new Map(
    ncpiPlatformStudies.map((study, index) => [index, study])
  );

  // Build platform aggregations
  const ncpiCatalogPlatforms = buildNCPICatalogPlatforms(ncpiPlatformStudies);

  await writeAsJSON(
    "catalog/ncpi-platform-studies.json",
    Object.fromEntries(studiesMap.entries())
  );

  await writeAsJSON(
    "catalog/ncpi-platforms.json",
    Object.fromEntries(ncpiCatalogPlatforms.entries())
  );

  console.log(`\nOutput files written:`);
  console.log(
    `  catalog/ncpi-platform-studies.json (${ncpiPlatformStudies.length} studies)`
  );
  console.log(`  catalog/ncpi-platforms.json`);
}

buildCatalog();
