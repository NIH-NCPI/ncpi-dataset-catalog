// Projects the full catalog JSON down to the fields the /studies list renders
// and writes a minified artifact. The studies list fetches this at runtime
// (SS_FETCH_CS_FILTERING), so it must carry only the list-column fields — the
// heavy detail-only fields (description, publications, variableSummary) are
// dropped here and instead come from props on the detail pages. See epic #425
// (stage 3b, #430). The full catalog stays the build-time input for
// seedDatabase and is emitted separately for rollback by sync-api.sh.
//
// Usage: node scripts/slim-list-artifact.mjs <src.json> <dest.json>

import { readFileSync, writeFileSync } from "fs";

import { KEEP_FIELDS } from "./list-artifact-fields.mjs";

const [, , srcPath, destPath] = process.argv;
if (!srcPath || !destPath) {
  console.error(
    "Usage: node scripts/slim-list-artifact.mjs <src.json> <dest.json>"
  );
  process.exit(1);
}

// Project each raw study record down to the kept list fields. Shape checks keep
// a corrupted catalog from failing with a low-signal TypeError.
const raw = JSON.parse(readFileSync(srcPath, "utf8"));
if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
  console.error(`${srcPath}: expected a JSON object keyed by study`);
  process.exit(1);
}
const slim = {};
for (const [id, study] of Object.entries(raw)) {
  if (typeof study !== "object" || study === null || Array.isArray(study)) {
    console.error(`${srcPath}: study ${id} is not an object`);
    process.exit(1);
  }
  const record = {};
  for (const field of KEEP_FIELDS) {
    if (field in study) record[field] = study[field];
  }
  slim[id] = record;
}

// Minified: no whitespace argument to stringify.
writeFileSync(destPath, JSON.stringify(slim));

console.log(
  `Slimmed ${Object.keys(slim).length} studies: ${srcPath} -> ${destPath}`
);
