/**
 * Test script for FHIR-first build.
 */

import { buildAllFHIRStudies } from "./build-fhir-studies";
import { writeAsJSON } from "./common/utils";

async function test(): Promise<void> {
  console.log("=== FHIR-First Build Test ===\n");

  const studies = await buildAllFHIRStudies();

  // Analyze results
  const byPlatform: Record<string, number> = {};
  let zeroParticipants = 0;
  let noDataTypes = 0;

  for (const s of studies) {
    for (const p of s.platforms) {
      byPlatform[p] = (byPlatform[p] || 0) + 1;
    }
    if (s.participantCount === 0) zeroParticipants++;
    if (s.dataTypes.length === 0) noDataTypes++;
  }

  console.log("\n=== Analysis ===");
  console.log("\nBy platform:");
  for (const [p, count] of Object.entries(byPlatform).sort()) {
    console.log(`  ${p}: ${count}`);
  }

  console.log(`\nStudies with 0 participants: ${zeroParticipants}`);
  console.log(`Studies with no data types: ${noDataTypes}`);

  // Write to temp file for comparison
  await writeAsJSON("/tmp/fhir-studies.json", studies);
  console.log("\nOutput written to /tmp/fhir-studies.json");

  // Sample some studies
  console.log("\n=== Sample Studies ===");
  const samples = studies.slice(0, 5);
  for (const s of samples) {
    console.log(`\n${s.dbGapId}: ${s.title}`);
    console.log(`  Participants: ${s.participantCount}`);
    console.log(`  Data Types: ${s.dataTypes.join(", ") || "(none)"}`);
    console.log(`  Platforms: ${s.platforms.join(", ")}`);
  }
}

test().catch(console.error);
