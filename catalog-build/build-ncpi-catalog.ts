import { writeAsJSON } from "./common/utils";
import { buildNCPICatalogPlatforms } from "./build-plaftorms";
import { buildAllFHIRStudies } from "./build-fhir-studies";

console.log("Building NCPI Catalog Data (FHIR-First)");
export {};

/**
 * Builds the NCPI catalog with ALL dbGaP studies.
 * Uses FHIR API as primary source for comprehensive coverage.
 * @returns void
 */
async function buildCatalog(): Promise<void> {
  // Build all dbGaP studies using FHIR-first approach
  const ncpiPlatformStudies = await buildAllFHIRStudies();

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
