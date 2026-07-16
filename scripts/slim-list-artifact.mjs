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

// Fields kept on each slim record: only the raw fields NCPIStudyInputMapper
// reads to build the list rows. consentLongNames is kept so the consent-code
// column keeps its tooltip. The detail-only fields (description, publications,
// variableSummary) are intentionally omitted — the detail pages source those
// from props instead.
const KEEP_FIELDS = [
  "consentCodes",
  "consentLongNames",
  "dataTypes",
  "dbGapId",
  "duosUrl",
  "focus",
  "gdcProjectId",
  "participantCount",
  "platforms",
  "studyAccession",
  "studyDesigns",
  "title",
];

const [, , srcPath, destPath] = process.argv;
if (!srcPath || !destPath) {
  console.error(
    "Usage: node scripts/slim-list-artifact.mjs <src.json> <dest.json>"
  );
  process.exit(1);
}

// Project each raw study record down to the kept list fields.
const raw = JSON.parse(readFileSync(srcPath, "utf8"));
const slim = {};
for (const [id, study] of Object.entries(raw)) {
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
