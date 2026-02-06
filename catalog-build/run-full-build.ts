import * as path from "path";
import { buildAllDbGapStudies } from "../catalog-build/build-all-dbgap-studies";
import { writeAsJSON } from "../catalog-build/common/utils";

async function main() {
  const studies = await buildAllDbGapStudies();
  const outPath = path.join(__dirname, "..", "catalog", "all-dbgap-studies.json");
  await writeAsJSON(outPath, studies);
  console.log(`\nWritten ${studies.length} studies to ${outPath}`);

  // Summary stats
  const parents = studies.filter(s => s.numChildren > 0);
  const children = studies.filter(s => s.parentStudyId);
  const standalone = studies.filter(s => !s.parentStudyId && s.numChildren === 0);
  console.log(`  Parents: ${parents.length}`);
  console.log(`  Children: ${children.length}`);
  console.log(`  Standalone: ${standalone.length}`);
}

main().catch(console.error);
