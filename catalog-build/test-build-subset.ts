/**
 * Test script to build a subset of studies.
 */

import { buildStudiesForIds } from "./build-all-dbgap-studies";
import { writeAsJSON } from "./common/utils";

const testIds = [
  "phs000007", // Framingham Heart Study - parent study
  "phs000342", // Framingham SHARe - child of phs000007
  "phs000220", // PAGE: MEC - from current catalog
  "phs000298", // Autism - from current catalog
  "phs000424", // GTEx - popular study
  "phs003460", // Recent study (phs003xxx range)
];

async function runTest() {
  console.log("Testing build with subset:", testIds);
  const studies = await buildStudiesForIds(testIds);

  console.log(`\n=== Built ${studies.length} studies ===\n`);

  for (const study of studies) {
    console.log(`${study.dbGapId}: ${study.title}`);
    console.log(`  Accession: ${study.studyAccession}`);
    console.log(`  Participants: ${study.participantCount}`);
    console.log(`  Focus: ${study.focus}`);
    console.log(`  Data Types: ${study.dataTypes.join(", ") || "(none)"}`);
    console.log(`  Consent Codes: ${study.consentCodes.join(", ")}`);
    console.log(`  Platforms: ${study.platforms.join(", ")}`);
    console.log(`  Parent: ${study.parentStudyId || "(none)"} ${study.parentStudyName || ""}`);
    console.log(`  Children: ${study.numChildren}`);
    console.log(`  dbGapUrl: ${study.dbGapUrl}`);
    console.log();
  }

  await writeAsJSON("/tmp/test-studies.json", studies);
  console.log("Output written to /tmp/test-studies.json");
}

runTest();
