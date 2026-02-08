/**
 * Fetch dbGaP "Selected Publications" from GapExchange XML + Semantic Scholar metadata
 *
 * Pipeline:
 * 1. For each dbGaP study, fetch GapExchange XML from FTP to get curated PMIDs
 * 2. Batch-resolve PMIDs via Semantic Scholar API for full metadata
 *    (title, authors, DOI, journal, citation counts, etc.)
 * 3. Output JSON mapping study IDs to their curated publications
 *
 * Requires: S2_API_KEY in .env file (free from https://www.semanticscholar.org/product/api)
 *
 * Usage:
 *   npx esrun catalog-build/fetch-dbgap-publications.ts [--test] [--limit=N] [--verbose]
 */

import * as fs from "fs";
import * as path from "path";
import {
  dbgapFtpBaseUrl,
  getLatestVersionXmlUrl,
  parseVersionsFromHtml,
} from "./common/dbGapCSVandFTP";

// --- Configuration ---

const FTP_DELAY_MS = 150;
const S2_DELAY_MS = 1100; // S2 batch: 1 req/sec with API key
const S2_BATCH_SIZE = 500; // S2 batch endpoint max
const S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch";
const S2_FIELDS = [
  "title",
  "authors",
  "year",
  "venue",
  "publicationDate",
  "journal",
  "externalIds",
  "citationCount",
  "influentialCitationCount",
  "publicationTypes",
  "openAccessPdf",
].join(",");

// --- Interfaces ---

interface S2Author {
  authorId: string;
  name: string;
}

interface S2Paper {
  paperId: string;
  externalIds: {
    DOI?: string;
    PubMed?: string;
    CorpusId?: number;
    MAG?: string;
  };
  title: string;
  authors: S2Author[];
  year: number;
  venue: string;
  publicationDate: string;
  journal?: {
    name: string;
    pages?: string;
    volume?: string;
  };
  citationCount: number;
  influentialCitationCount: number;
  publicationTypes?: string[];
  openAccessPdf?: {
    url: string;
    status: string;
  };
}

interface StudyPublications {
  phsId: string;
  studyName: string;
  ftpVersion: string;
  pmids: number[];
  publications: S2Paper[];
  pmidsNotInS2: number[];
  fetchedAt: string;
}

interface PipelineResults {
  fetchedAt: string;
  studies: StudyPublications[];
  totalNotInS2: number;
  totalPmids: number;
  totalResolved: number;
  totalStudies: number;
  studiesWithPublications: number;
}

// --- Utilities ---

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadEnvFile(): void {
  const envPath = path.join(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, "utf-8").split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

// --- Phase 1: Fetch PMIDs from GapExchange XML ---

/**
 * Parse PMIDs from GapExchange XML content.
 * Extracts all <Pubmed pmid="XXXXX"/> entries.
 */
function parsePmidsFromXml(xml: string): number[] {
  const pmids: number[] = [];
  const pattern = /<Pubmed\s+pmid="(\d+)"\s*\/?>/g;
  let match;
  while ((match = pattern.exec(xml)) !== null) {
    pmids.push(parseInt(match[1], 10));
  }
  return pmids;
}

/**
 * Fetch PMIDs for a single study from the dbGaP FTP server.
 * Returns the list of PMIDs and the FTP version used.
 */
async function fetchStudyPmids(
  phsId: string,
  verbose: boolean
): Promise<{ pmids: number[]; ftpVersion: string }> {
  // Fetch FTP directory listing to find available versions
  const dirUrl = `${dbgapFtpBaseUrl}/${phsId}/`;
  const dirResponse = await fetch(dirUrl);

  if (!dirResponse.ok) {
    if (verbose) console.log(`    FTP directory not found for ${phsId}`);
    return { pmids: [], ftpVersion: "" };
  }

  const dirHtml = await dirResponse.text();
  const versions = parseVersionsFromHtml(dirHtml, phsId);
  const xmlUrl = getLatestVersionXmlUrl(phsId, versions);

  if (!xmlUrl) {
    if (verbose) console.log(`    No versions found for ${phsId}`);
    return { pmids: [], ftpVersion: "" };
  }

  // Extract version string from URL for metadata
  const versionMatch = xmlUrl.match(/\.(v\d+\.p\d+)\./);
  const ftpVersion = versionMatch ? versionMatch[1] : "";

  await sleep(FTP_DELAY_MS);

  // Fetch the GapExchange XML
  const xmlResponse = await fetch(xmlUrl);
  if (!xmlResponse.ok) {
    if (verbose) console.log(`    XML not found: ${xmlUrl}`);
    return { pmids: [], ftpVersion };
  }

  const xml = await xmlResponse.text();
  const pmids = parsePmidsFromXml(xml);

  return { pmids, ftpVersion };
}

// --- Phase 2: Resolve PMIDs via Semantic Scholar ---

/**
 * Batch-resolve PMIDs using Semantic Scholar's /paper/batch endpoint.
 * Returns a map from PMID to S2 paper metadata.
 */
async function resolveViaSemantic(
  allPmids: number[],
  apiKey: string,
  verbose: boolean
): Promise<Map<number, S2Paper>> {
  const results = new Map<number, S2Paper>();

  for (let i = 0; i < allPmids.length; i += S2_BATCH_SIZE) {
    const batch = allPmids.slice(i, i + S2_BATCH_SIZE);
    const ids = batch.map((pmid) => `PMID:${pmid}`);

    const batchNum = Math.floor(i / S2_BATCH_SIZE) + 1;
    const totalBatches = Math.ceil(allPmids.length / S2_BATCH_SIZE);

    if (verbose) {
      console.log(
        `  S2 batch ${batchNum}/${totalBatches}: ${batch.length} PMIDs`
      );
    }

    const response = await fetch(`${S2_BATCH_URL}?fields=${S2_FIELDS}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
      },
      body: JSON.stringify({ ids }),
    });

    if (!response.ok) {
      const body = await response.text();
      console.error(
        `  S2 batch ${batchNum} failed: ${response.status} — ${body.slice(0, 200)}`
      );
      // Continue with remaining batches
      await sleep(S2_DELAY_MS);
      continue;
    }

    const papers: (S2Paper | null)[] = await response.json();

    // S2 batch returns results in the same order as input IDs.
    // Null entries mean the paper was not found.
    for (let j = 0; j < papers.length; j++) {
      const paper = papers[j];
      if (paper) {
        results.set(batch[j], paper);
      }
    }

    if (i + S2_BATCH_SIZE < allPmids.length) {
      await sleep(S2_DELAY_MS);
    }
  }

  return results;
}

// --- Study loader (same pattern as other scripts) ---

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
  { phsId: "phs000007", studyName: "Framingham Cohort" },
  { phsId: "phs000209", studyName: "Multi-Ethnic Study of Atherosclerosis (MESA)" },
  { phsId: "phs000280", studyName: "Atherosclerosis Risk in Communities (ARIC)" },
  { phsId: "phs000956", studyName: "Amish Studies" },
  { phsId: "phs000668", studyName: "Eosinophilic Esophagitis (EoE) Genetics" },
];

// --- Main ---

async function main(): Promise<void> {
  loadEnvFile();

  const apiKey = process.env.S2_API_KEY;
  if (!apiKey) {
    console.error("S2_API_KEY not found. Add it to .env or export it.");
    process.exit(1);
  }

  const args = process.argv.slice(2);
  const testMode = args.includes("--test");
  const verbose = args.includes("--verbose");
  const limitArg = args.find((a) => a.startsWith("--limit="));
  const limit = limitArg ? parseInt(limitArg.split("=")[1], 10) : undefined;

  console.log("=".repeat(60));
  console.log("dbGaP Selected Publications (GapExchange XML + Semantic Scholar)");
  console.log("=".repeat(60));
  console.log(`Mode: ${testMode ? "TEST" : "FULL"}`);
  console.log(`Verbose: ${verbose ? "ON" : "OFF"}`);
  console.log(`Study limit: ${limit || "none"}`);
  console.log();

  // Step 1: Load study list
  let studies = testMode ? TEST_STUDIES : loadStudyIds();
  console.log(
    `Loaded ${studies.length} studies ${testMode ? "(test set)" : "from catalog"}`
  );

  if (limit) {
    studies = studies.slice(0, limit);
    console.log(`Limited to ${studies.length} studies`);
  }

  // Step 2: Fetch PMIDs from FTP for each study
  console.log();
  console.log("Phase 1: Fetching PMIDs from GapExchange XML...");
  console.log("-".repeat(40));

  const studyPmidData: Array<{
    phsId: string;
    studyName: string;
    pmids: number[];
    ftpVersion: string;
  }> = [];

  let totalPmids = 0;
  let studiesWithPubs = 0;

  for (let i = 0; i < studies.length; i++) {
    const study = studies[i];
    const progress = `[${i + 1}/${studies.length}]`;

    try {
      const { pmids, ftpVersion } = await fetchStudyPmids(
        study.phsId,
        verbose
      );

      studyPmidData.push({
        phsId: study.phsId,
        studyName: study.studyName,
        pmids,
        ftpVersion,
      });

      totalPmids += pmids.length;
      if (pmids.length > 0) studiesWithPubs++;

      console.log(
        `${progress} ${study.phsId}: ${pmids.length} PMIDs (${ftpVersion}) — ${study.studyName.slice(0, 50)}`
      );
    } catch (error) {
      console.error(`${progress} ${study.phsId}: FTP ERROR — ${error}`);
      studyPmidData.push({
        phsId: study.phsId,
        studyName: study.studyName,
        pmids: [],
        ftpVersion: "",
      });
    }

    await sleep(FTP_DELAY_MS);
  }

  console.log();
  console.log(
    `Phase 1 complete: ${totalPmids} PMIDs across ${studiesWithPubs} studies`
  );

  // Step 3: Collect unique PMIDs and resolve via S2
  const allUniquePmids = [
    ...new Set(studyPmidData.flatMap((s) => s.pmids)),
  ].sort((a, b) => a - b);

  console.log(`Unique PMIDs to resolve: ${allUniquePmids.length}`);
  console.log();
  console.log("Phase 2: Resolving metadata via Semantic Scholar...");
  console.log("-".repeat(40));

  const s2Results = await resolveViaSemantic(allUniquePmids, apiKey, verbose);

  console.log();
  console.log(
    `Phase 2 complete: ${s2Results.size}/${allUniquePmids.length} resolved`
  );

  // Step 4: Build output
  const studyResults: StudyPublications[] = [];

  for (const data of studyPmidData) {
    const publications: S2Paper[] = [];
    const pmidsNotInS2: number[] = [];

    for (const pmid of data.pmids) {
      const paper = s2Results.get(pmid);
      if (paper) {
        publications.push(paper);
      } else {
        pmidsNotInS2.push(pmid);
      }
    }

    // Sort by citation count descending
    publications.sort((a, b) => (b.citationCount || 0) - (a.citationCount || 0));

    studyResults.push({
      phsId: data.phsId,
      studyName: data.studyName,
      ftpVersion: data.ftpVersion,
      pmids: data.pmids,
      publications,
      pmidsNotInS2,
      fetchedAt: new Date().toISOString(),
    });
  }

  const totalNotInS2 = studyResults.reduce(
    (sum, s) => sum + s.pmidsNotInS2.length,
    0
  );

  const pipelineResults: PipelineResults = {
    fetchedAt: new Date().toISOString(),
    studies: studyResults.sort(
      (a, b) => b.publications.length - a.publications.length
    ),
    totalNotInS2,
    totalPmids,
    totalResolved: s2Results.size,
    totalStudies: studies.length,
    studiesWithPublications: studiesWithPubs,
  };

  const outputPath = path.join(
    __dirname,
    "..",
    "catalog",
    "dbgap-publications.json"
  );
  fs.writeFileSync(outputPath, JSON.stringify(pipelineResults, null, 2));

  console.log();
  console.log("=".repeat(60));
  console.log("Pipeline Complete");
  console.log("=".repeat(60));
  console.log(`Total studies processed: ${pipelineResults.totalStudies}`);
  console.log(`Studies with publications: ${studiesWithPubs}`);
  console.log(`Total PMIDs from XML: ${totalPmids}`);
  console.log(`Unique PMIDs resolved via S2: ${s2Results.size}`);
  console.log(`PMIDs not found in S2: ${totalNotInS2}`);
  console.log(`Output: ${outputPath}`);
}

main().catch(console.error);
