import { parseContentRows, readFile } from "../../app/utils/tsvParser";
import { SOURCE_FIELD_KEY, SOURCE_FIELD_TYPE } from "./tsv-config";
import { writeAsJSON } from "../common/utils";
import { buildAnVILCatalogStudies } from "./build-studies";
import { AnVILCatalog, buildAnVILCatalogWorkspaces } from "./build-workspaces";

console.log("Building AnVIL Catalog Data");
export {};

const tsvPath = "anvil-catalog/files/dashboard-source-anvil.tsv";

/**
 * Load the workspace TSV, read in associated FHIR studies, join them and save.
 */
async function buildCatalog(): Promise<void> {
  const file = await readFile(tsvPath);
  if (!file) {
    throw new Error(`File ${tsvPath} not found`);
  }

  const tsvWorkspacesTMP = await parseContentRows(
    file,
    "\t",
    SOURCE_FIELD_KEY,
    SOURCE_FIELD_TYPE
  );

  const tsvWorkspaces = tsvWorkspacesTMP;

  if (!tsvWorkspaces) {
    throw new Error(`Error parsing ${tsvPath}.`);
  }

  console.log(tsvWorkspaces.length);

  /**
   * Build the workspaces and studies
   */
  const anVILCatalogWorkspaces = await buildAnVILCatalogWorkspaces(
    tsvWorkspaces as AnVILCatalog[]
  );
  const studiesByStudyId = await buildAnVILCatalogStudies(
    anVILCatalogWorkspaces
  );
  const studies = [...studiesByStudyId.values()];

  /**
   * Write out the resulting study files
   */

  console.log("Studies:", studies.length);
  await writeAsJSON(
    "anvil-catalog/out/anvil-studies.json",
    Object.fromEntries(studies.entries())
  );
}

buildCatalog();
