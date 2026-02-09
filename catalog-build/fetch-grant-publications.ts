/**
 * Fetch grant-linked publications from NIH Reporter API
 *
 * These are publications linked to NIH grants whose title, abstract, or
 * terms mention the study name. Found via the NIH Reporter API, not from
 * the study's own metadata. Produces a broader set than the PI-curated
 * "Selected Publications" in GapExchange XML.
 *
 * Pipeline:
 * 1. For each dbGaP study, search NIH Reporter for grants mentioning the study name
 * 2. Collect all core project numbers from matching grants
 * 3. Fetch publications (PMIDs) linked to those grants via Reporter
 * 4. Output catalog/grant-publications.json
 *
 * Usage:
 *   npx esrun catalog-build/fetch-grant-publications.ts [--test] [--stress] [--limit=N] [--verbose]
 */

import * as fs from "fs";
import * as path from "path";

// Reporter recommends no more than 1 request per second
const DELAY_MS = 1100;

const REPORTER_PROJECTS_URL =
  "https://api.reporter.nih.gov/v2/projects/search";
const REPORTER_PUBLICATIONS_URL =
  "https://api.reporter.nih.gov/v2/publications/search";

interface ReporterGrant {
  coreProjectNum: string;
  projectTitle: string;
}

interface ReporterPublication {
  pmid: number;
  coreProjectNum: string;
  applId: number;
}

interface StudyGrants {
  phsId: string;
  studyName: string;
  searchQuery: string;
  grants: ReporterGrant[];
  publications: ReporterPublication[];
  uniquePmids: number[];
  fetchedAt: string;
}

interface PipelineResults {
  totalStudies: number;
  studiesWithGrants: number;
  studiesWithPublications: number;
  totalGrants: number;
  totalPublications: number;
  totalUniquePmids: number;
  fetchedAt: string;
  studies: StudyGrants[];
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Search Reporter across all text fields (title, abstract, terms)
 * for the study name. Returns deduplicated grants.
 */
async function searchGrantsByStudyName(
  searchQuery: string,
  verbose: boolean
): Promise<ReporterGrant[]> {
  const allGrants: ReporterGrant[] = [];
  let offset = 0;
  const limit = 500;

  while (true) {
    const body = {
      criteria: {
        advanced_text_search: {
          operator: "and",
          search_field: "projecttitle,terms,abstracttext",
          search_text: `"${searchQuery}"`,
        },
      },
      offset,
      limit,
      include_fields: ["CoreProjectNum", "ProjectTitle"],
    };

    const response = await fetch(REPORTER_PROJECTS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Reporter projects search failed: ${response.status}`);
    }

    const data = await response.json();
    const results = data.results || [];
    const total = data.meta?.total || 0;

    if (verbose && offset === 0) {
      console.log(`    ${total} projects match "${searchQuery}"`);
    }

    for (const r of results) {
      allGrants.push({
        coreProjectNum: r.core_project_num || "",
        projectTitle: r.project_title || "",
      });
    }

    if (results.length < limit || allGrants.length >= total) break;
    offset += limit;
    await sleep(DELAY_MS);
  }

  // Deduplicate by core project number
  const seen = new Set<string>();
  return allGrants.filter((g) => {
    if (!g.coreProjectNum || seen.has(g.coreProjectNum)) return false;
    seen.add(g.coreProjectNum);
    return true;
  });
}

/**
 * Clean a study name for Reporter search.
 * Strips common catalog prefixes and parentheticals to extract
 * the core study name for a quoted phrase search.
 */
function cleanStudyName(rawName: string): string {
  let name = rawName;

  // Strip common catalog prefixes
  const prefixes = [
    /^NHLBI\s+TOPMed\s*[-–:]\s*/i,
    /^NHGRI\s+CCDG\s*[-–:]\s*/i,
    /^Center\s+(?:for\s+)?Common\s+Disease\s+Genomics\s*\[?CCDG\]?\s*[-–:]\s*/i,
    /^CCDG\s*[-–:]*\s*/i,
    /^(?:Cardiovascular|Neuropsychiatric|CVD)\s*[-–:]\s*/i,
    /^PAGE\s*[-–:]\s*/i,
    /^Common\s+Fund\s*\(CF\)\s*/i,
  ];

  for (const prefix of prefixes) {
    name = name.replace(prefix, "");
  }

  // Strip from the first parenthetical onward
  // "Atherosclerosis Risk in Communities (ARIC)" -> "Atherosclerosis Risk in Communities"
  // "Pediatric Cardiac Genomics Consortium (PCGC)'s Biobank" -> "Pediatric Cardiac Genomics Consortium"
  name = name.replace(/\s*\([^)]*\).*$/, "");

  // Strip bracketed acronyms
  name = name.replace(/\s*\[[^\]]{1,10}\]\s*/g, " ");

  // Remove trailing substudy info
  name = name.replace(
    /\s*[-–]\s*(?:Task Area|Phase|Renewal|Supplement).*$/i,
    ""
  );

  // Collapse whitespace (catalog names sometimes have extra spaces)
  name = name.replace(/\s+/g, " ");

  // Trim and remove quotes that would break the search
  name = name.replace(/"/g, "").trim();

  // If name is too short, skip
  if (name.length < 5) return "";

  return name;
}

/**
 * Fetch publications linked to a set of core project numbers.
 * Batches grants into chunks to avoid server errors with large lists.
 */
async function fetchPublicationsForGrants(
  coreProjectNums: string[],
  verbose: boolean
): Promise<ReporterPublication[]> {
  if (coreProjectNums.length === 0) return [];

  const GRANT_BATCH_SIZE = 25;
  const allPubs: ReporterPublication[] = [];
  let totalReported = 0;

  for (let g = 0; g < coreProjectNums.length; g += GRANT_BATCH_SIZE) {
    const grantBatch = coreProjectNums.slice(g, g + GRANT_BATCH_SIZE);
    let offset = 0;
    const limit = 500;

    while (true) {
      const body = {
        criteria: {
          core_project_nums: grantBatch,
        },
        offset,
        limit,
      };

      const response = await fetch(REPORTER_PUBLICATIONS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error(
          `Reporter publications search failed: ${response.status}`
        );
      }

      const data = await response.json();
      const results = data.results || [];
      const total = data.meta?.total || 0;

      if (offset === 0) totalReported += total;

      for (const r of results) {
        allPubs.push({
          pmid: r.pmid,
          coreProjectNum: r.coreproject || "",
          applId: r.applid || 0,
        });
      }

      if (results.length < limit || offset + results.length >= total) break;
      offset += limit;
      await sleep(DELAY_MS);
    }

    await sleep(DELAY_MS);
  }

  if (verbose) {
    console.log(
      `    ${totalReported} publications across ${coreProjectNums.length} grants`
    );
  }

  return allPubs;
}

/**
 * Process a single study end-to-end.
 */
async function processStudy(
  phsId: string,
  studyName: string,
  verbose: boolean
): Promise<StudyGrants> {
  const searchQuery = cleanStudyName(studyName);

  if (!searchQuery) {
    if (verbose) console.log(`    Skipping — name too short after cleaning`);
    return {
      phsId,
      studyName,
      searchQuery: "",
      grants: [],
      publications: [],
      uniquePmids: [],
      fetchedAt: new Date().toISOString(),
    };
  }

  // Step 1: Find grants
  const grants = await searchGrantsByStudyName(searchQuery, verbose);
  await sleep(DELAY_MS);

  if (grants.length === 0) {
    return {
      phsId,
      studyName,
      searchQuery,
      grants: [],
      publications: [],
      uniquePmids: [],
      fetchedAt: new Date().toISOString(),
    };
  }

  // Step 2: Fetch publications for all grants
  const coreNums = grants.map((g) => g.coreProjectNum);
  const publications = await fetchPublicationsForGrants(coreNums, verbose);
  await sleep(DELAY_MS);

  // Step 3: Deduplicate PMIDs
  const pmidSet = new Set<number>();
  for (const pub of publications) {
    pmidSet.add(pub.pmid);
  }
  const uniquePmids = Array.from(pmidSet).sort((a, b) => a - b);

  return {
    phsId,
    studyName,
    searchQuery,
    grants,
    publications,
    uniquePmids,
    fetchedAt: new Date().toISOString(),
  };
}

/**
 * Load study IDs from the catalog.
 */
function loadStudyIds(): Array<{ phsId: string; studyName: string }> {
  const catalogPath = path.join(
    __dirname,
    "..",
    "catalog",
    "ncpi-platform-studies.json"
  );

  if (!fs.existsSync(catalogPath)) {
    console.error("Catalog file not found:", catalogPath);
    return [];
  }

  const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf-8"));
  const studies: Array<{ phsId: string; studyName: string }> = [];
  const studyList = Array.isArray(catalog) ? catalog : Object.values(catalog);

  for (const study of studyList as Array<{
    dbGapId?: string;
    title?: string;
    studyName?: string;
  }>) {
    if (study.dbGapId) {
      const match = study.dbGapId.match(/phs\d+/);
      if (match) {
        studies.push({
          phsId: match[0],
          studyName: study.title || study.studyName || "",
        });
      }
    }
  }

  // Deduplicate by phsId (keep first occurrence with longest name)
  const byPhs = new Map<string, string>();
  for (const s of studies) {
    const existing = byPhs.get(s.phsId);
    if (!existing || s.studyName.length > existing.length) {
      byPhs.set(s.phsId, s.studyName);
    }
  }

  return Array.from(byPhs.entries()).map(([phsId, studyName]) => ({
    phsId,
    studyName,
  }));
}

const TEST_STUDIES = [
  { phsId: "phs000007", studyName: "Framingham Heart Study" },
  { phsId: "phs000286", studyName: "Jackson Heart Study" },
  {
    phsId: "phs000209",
    studyName: "Multi-Ethnic Study of Atherosclerosis (MESA)",
  },
  {
    phsId: "phs000280",
    studyName: "Atherosclerosis Risk in Communities (ARIC)",
  },
  { phsId: "phs000287", studyName: "Cleveland Family Study" },
];

// Diverse stress test
const STRESS_STUDIES = [
  // Prefixed
  { phsId: "phs001612", studyName: "NHLBI TOPMed: Coronary Artery Risk Development in Young Adults (CARDIA)" },
  { phsId: "phs000997", studyName: "NHLBI TOPMed - NHGRI CCDG: The Vanderbilt AF Ablation Registry" },
  { phsId: "phs001735", studyName: "NHLBI TOPMed: Pediatric Cardiac Genomics Consortium (PCGC)'s Congenital Heart Disease Biobank" },
  // Acronyms (previously problematic)
  { phsId: "phs001726", studyName: "NHLBI TOPMed: Childhood Asthma Management Program (CAMP)" },
  { phsId: "phs000092", studyName: "Study of Addiction: Genetics and Environment (SAGE)" },
  { phsId: "phs000166", studyName: "SNP Health Association Resource (SHARe) Asthma Resource Project (SHARP)" },
  // Lesser-known
  { phsId: "phs000703", studyName: "CATHeterization GENetics (CATHGEN)" },
  { phsId: "phs000629", studyName: "GWAS of Familial Lung Cancer" },
  { phsId: "phs001691", studyName: "Pittsburgh Heterotaxy Study" },
  // Major studies
  { phsId: "phs000424", studyName: "Common Fund (CF) Genotype-Tissue Expression Project (GTEx)" },
  { phsId: "phs000200", studyName: "Women's Health Initiative" },
];

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const testMode = args.includes("--test");
  const stressMode = args.includes("--stress");
  const verbose = args.includes("--verbose");
  const limitArg = args.find((a) => a.startsWith("--limit="));
  const limit = limitArg ? parseInt(limitArg.split("=")[1], 10) : undefined;

  console.log("=".repeat(60));
  console.log("NIH Reporter: Grant-Linked Publication Discovery");
  console.log("=".repeat(60));
  console.log(`Mode: ${stressMode ? "STRESS TEST" : testMode ? "TEST" : "FULL"}`);
  console.log(`Verbose: ${verbose ? "ON" : "OFF"}`);
  console.log(`Study limit: ${limit || "none"}`);
  console.log();

  let studies = stressMode
    ? STRESS_STUDIES
    : testMode
      ? TEST_STUDIES
      : loadStudyIds();
  console.log(
    `Loaded ${studies.length} studies ${stressMode ? "(stress set)" : testMode ? "(test set)" : "from catalog"}`
  );

  if (limit) {
    studies = studies.slice(0, limit);
    console.log(`Limited to ${studies.length} studies`);
  }

  const results: StudyGrants[] = [];
  let totalGrants = 0;
  let totalPmids = 0;
  let studiesWithGrants = 0;
  let studiesWithPubs = 0;

  for (let i = 0; i < studies.length; i++) {
    const study = studies[i];
    const progress = `[${i + 1}/${studies.length}]`;

    try {
      const result = await processStudy(study.phsId, study.studyName, verbose);
      results.push(result);

      totalGrants += result.grants.length;
      totalPmids += result.uniquePmids.length;
      if (result.grants.length > 0) studiesWithGrants++;
      if (result.uniquePmids.length > 0) studiesWithPubs++;

      console.log(
        `${progress} ${study.phsId}: ${result.grants.length} grants, ${result.uniquePmids.length} publications — ${study.studyName.slice(0, 50)}`
      );
    } catch (error) {
      console.error(`${progress} ${study.phsId}: ERROR - ${error}`);
      results.push({
        phsId: study.phsId,
        studyName: study.studyName,
        searchQuery: "",
        grants: [],
        publications: [],
        uniquePmids: [],
        fetchedAt: new Date().toISOString(),
      });
    }
  }

  const pipelineResults: PipelineResults = {
    totalStudies: studies.length,
    studiesWithGrants,
    studiesWithPublications: studiesWithPubs,
    totalGrants,
    totalPublications: results.reduce(
      (sum, r) => sum + r.publications.length,
      0
    ),
    totalUniquePmids: totalPmids,
    fetchedAt: new Date().toISOString(),
    studies: results.sort((a, b) => b.uniquePmids.length - a.uniquePmids.length),
  };

  const outputPath = path.join(
    __dirname,
    "..",
    "catalog",
    "grant-publications.json"
  );
  fs.writeFileSync(outputPath, JSON.stringify(pipelineResults, null, 2));

  console.log();
  console.log("=".repeat(60));
  console.log("Pipeline Complete");
  console.log("=".repeat(60));
  console.log(`Total studies processed: ${pipelineResults.totalStudies}`);
  console.log(`Studies with grants: ${studiesWithGrants}`);
  console.log(`Studies with publications: ${studiesWithPubs}`);
  console.log(`Total unique grants: ${totalGrants}`);
  console.log(`Total unique PMIDs: ${totalPmids}`);
  console.log(`Output: ${outputPath}`);
}

main().catch(console.error);
