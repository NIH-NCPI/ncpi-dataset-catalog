/**
 * Patches variableSummary into an existing ncpi-platform-studies.json
 * without re-running the full catalog build.
 *
 * Usage: npx esrun catalog-build/patch-variable-summaries.ts
 */
import fs from "fs";
import { loadVariableSummaries } from "./build-variable-summary";

const STUDIES_PATH = "catalog/ncpi-platform-studies.json";

const studies = JSON.parse(fs.readFileSync(STUDIES_PATH, "utf-8"));
const summaries = loadVariableSummaries(
  "catalog-build/classification/output"
);

if (summaries.size === 0) {
  console.error("No variable summaries loaded — aborting to avoid wiping existing data.");
  process.exit(1);
}

let patched = 0;
for (const study of Object.values(studies) as Record<string, unknown>[]) {
  const id = study.dbGapId as string;
  const summary = summaries.get(id);
  if (summary) {
    study.variableSummary = summary;
    patched++;
  }
}

fs.writeFileSync(STUDIES_PATH, JSON.stringify(studies, null, 2));
console.log(
  `Patched variable summaries: ${patched} of ${Object.keys(studies).length} studies`
);
