/**
 * Fetch publications that cite dbGaP studies
 *
 * Pipeline:
 * 1. Search PMC for papers citing each dbGaP accession (phs######)
 * 2. Fetch metadata for those papers (title, authors, journal, year)
 * 3. Optionally fetch full text and extract Methods section
 * 4. Output JSON mapping study IDs to their citing publications
 *
 * Usage:
 *   npx esrun catalog-build/fetch-study-publications.ts [--full-text] [--limit=N]
 */

import * as fs from "fs";
import * as path from "path";

// Rate limiting: NCBI requests 3 requests/second without API key
const DELAY_MS = 350;

interface Publication {
  phsId: string; // Link back to study
  pmcid: string;
  pmid?: string;
  doi?: string;
  title: string;
  authors: string[];
  journal: string;
  year: number;
  abstract?: string;
  methodsExcerpt?: string;
  fullTextAvailable: boolean;
}

interface StudyPublications {
  phsId: string;
  studyName?: string;
  publicationCount: number;
  publications: Publication[];
  fetchedAt: string;
}

interface PipelineResults {
  totalStudies: number;
  totalPublications: number;
  studiesWithPublications: number;
  fetchedAt: string;
  studies: StudyPublications[];
}

/**
 * Sleep for rate limiting
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Search PMC for papers citing a dbGaP accession
 */
async function searchPMCForStudy(
  phsId: string
): Promise<{ count: number; pmcIds: string[] }> {
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term=${phsId}&retmode=json&retmax=500`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`PMC search failed for ${phsId}: ${response.status}`);
  }

  const data = await response.json();
  const count = parseInt(data.esearchresult?.count || "0", 10);
  const pmcIds: string[] = data.esearchresult?.idlist || [];

  return { count, pmcIds };
}

/**
 * Fetch metadata for a batch of PMC IDs
 */
async function fetchPMCMetadata(
  pmcIds: string[],
  phsId: string
): Promise<Map<string, Publication>> {
  if (pmcIds.length === 0) return new Map();

  const idsParam = pmcIds.join(",");
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id=${idsParam}&retmode=json`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`PMC metadata fetch failed: ${response.status}`);
  }

  const data = await response.json();
  const results = new Map<string, Publication>();

  for (const pmcId of pmcIds) {
    const record = data.result?.[pmcId];
    if (!record) continue;

    // Parse authors
    const authors: string[] = [];
    if (record.authors) {
      for (const author of record.authors) {
        if (author.name) {
          authors.push(author.name);
        }
      }
    }

    // Parse year from pubdate
    const pubdate = record.pubdate || "";
    const yearMatch = pubdate.match(/(\d{4})/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : 0;

    // Extract DOI and PMID from articleids
    let doi: string | undefined;
    let pmid: string | undefined;
    if (record.articleids) {
      for (const id of record.articleids) {
        if (id.idtype === "doi") doi = id.value;
        if (id.idtype === "pmid") pmid = id.value;
      }
    }

    results.set(pmcId, {
      phsId, // Link back to study
      pmcid: `PMC${pmcId}`,
      pmid,
      doi,
      title: record.title || "(no title)",
      authors,
      journal: record.source || record.fulljournalname || "",
      year,
      fullTextAvailable: false, // Will be updated if we fetch full text
    });
  }

  return results;
}

/**
 * Fetch abstracts from PubMed for a batch of PMIDs (faster than full text)
 */
async function fetchAbstracts(pmids: string[]): Promise<Map<string, string>> {
  if (pmids.length === 0) return new Map();

  const idsParam = pmids.join(",");
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${idsParam}&rettype=xml`;

  const response = await fetch(url);
  if (!response.ok) {
    return new Map();
  }

  const xml = await response.text();
  const results = new Map<string, string>();

  // Parse each article's abstract
  const articleMatches = xml.matchAll(
    /<PubmedArticle>[\s\S]*?<PMID[^>]*>(\d+)<\/PMID>[\s\S]*?<\/PubmedArticle>/g
  );

  for (const match of articleMatches) {
    const pmid = match[1];
    const articleXml = match[0];

    // Extract abstract text (handles both simple and labeled abstracts)
    const abstractMatch = articleXml.match(/<Abstract>([\s\S]*?)<\/Abstract>/i);
    if (abstractMatch) {
      const abstract = stripXmlTags(abstractMatch[1]).trim().slice(0, 2000);
      if (abstract) {
        results.set(pmid, abstract);
      }
    }
  }

  return results;
}

/**
 * Fetch full text XML and extract abstract + methods
 */
async function fetchFullText(
  pmcId: string
): Promise<{ abstract?: string; methodsExcerpt?: string } | null> {
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=${pmcId}&rettype=xml`;

  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }

  const xml = await response.text();

  // Check if it's actually full text (not just metadata)
  if (!xml.includes("<body>") && !xml.includes("<sec")) {
    return null;
  }

  // Simple XML text extraction (avoiding heavy XML parser dependency)
  let abstract: string | undefined;
  let methodsExcerpt: string | undefined;

  // Extract abstract
  const abstractMatch = xml.match(/<abstract[^>]*>([\s\S]*?)<\/abstract>/i);
  if (abstractMatch) {
    abstract = stripXmlTags(abstractMatch[1]).trim().slice(0, 2000);
  }

  // Extract methods section
  const methodsMatch = xml.match(
    /<sec[^>]*>[\s\S]*?<title[^>]*>[^<]*Method[^<]*<\/title>([\s\S]*?)<\/sec>/i
  );
  if (methodsMatch) {
    methodsExcerpt = stripXmlTags(methodsMatch[1]).trim().slice(0, 3000);
  }

  return { abstract, methodsExcerpt };
}

/**
 * Strip XML tags from text
 */
function stripXmlTags(xml: string): string {
  return xml
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Process a single study - search and fetch publications
 */
async function processStudy(
  phsId: string,
  studyName: string | undefined,
  fetchFullTextContent: boolean,
  skipAbstracts: boolean
): Promise<StudyPublications> {
  // Search PMC for citing papers
  const { count, pmcIds } = await searchPMCForStudy(phsId);
  await sleep(DELAY_MS);

  if (pmcIds.length === 0) {
    return {
      phsId,
      studyName,
      publicationCount: count,
      publications: [],
      fetchedAt: new Date().toISOString(),
    };
  }

  // Fetch metadata in batches of 100
  const allPublications: Publication[] = [];
  for (let i = 0; i < pmcIds.length; i += 100) {
    const batch = pmcIds.slice(i, i + 100);
    const metadata = await fetchPMCMetadata(batch, phsId);

    for (const [, pub] of metadata) {
      allPublications.push(pub);
    }
    await sleep(DELAY_MS);
  }

  // Fetch abstracts from PubMed (fast, doesn't require full text)
  if (!skipAbstracts) {
    const pmidsToFetch = allPublications
      .filter((p) => p.pmid)
      .map((p) => p.pmid as string);

    // Batch fetch abstracts (100 at a time)
    for (let i = 0; i < pmidsToFetch.length; i += 100) {
      const batch = pmidsToFetch.slice(i, i + 100);
      const abstracts = await fetchAbstracts(batch);

      // Add abstracts to publications
      for (const pub of allPublications) {
        if (pub.pmid && abstracts.has(pub.pmid)) {
          pub.abstract = abstracts.get(pub.pmid);
        }
      }
      await sleep(DELAY_MS);
    }
  }

  // Optionally fetch full text for top publications (methods section)
  if (fetchFullTextContent) {
    // Only fetch full text for first 10 to avoid rate limits
    const toFetch = allPublications.slice(0, 10);
    for (const pub of toFetch) {
      const pmcIdNum = pub.pmcid.replace("PMC", "");
      const fullText = await fetchFullText(pmcIdNum);
      if (fullText) {
        pub.fullTextAvailable = true;
        if (fullText.abstract) pub.abstract = fullText.abstract;
        pub.methodsExcerpt = fullText.methodsExcerpt;
      }
      await sleep(DELAY_MS);
    }
  }

  // Sort by year descending (most recent first)
  allPublications.sort((a, b) => b.year - a.year);

  return {
    phsId,
    studyName,
    publicationCount: count,
    publications: allPublications,
    fetchedAt: new Date().toISOString(),
  };
}

/**
 * Load study IDs from the catalog
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

  // Catalog is an object with numeric keys, not an array
  const studyList = Array.isArray(catalog) ? catalog : Object.values(catalog);

  for (const study of studyList as Array<{
    dbGapId?: string;
    title?: string;
    studyName?: string;
  }>) {
    if (study.dbGapId) {
      // Extract base phs ID (without version)
      const match = study.dbGapId.match(/phs\d+/);
      if (match) {
        studies.push({
          phsId: match[0],
          studyName: study.title || study.studyName || "",
        });
      }
    }
  }

  // Deduplicate by phsId
  const seen = new Set<string>();
  return studies.filter((s) => {
    if (seen.has(s.phsId)) return false;
    seen.add(s.phsId);
    return true;
  });
}

/**
 * Well-known test studies for validation
 */
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

/**
 * Main pipeline
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const fetchFullTextContent = args.includes("--full-text");
  const skipAbstracts = args.includes("--skip-abstracts");
  const testMode = args.includes("--test");
  const limitArg = args.find((a) => a.startsWith("--limit="));
  const limit = limitArg ? parseInt(limitArg.split("=")[1], 10) : undefined;

  console.log("=".repeat(60));
  console.log("dbGaP Study Publication Discovery Pipeline");
  console.log("=".repeat(60));
  console.log(`Abstracts: ${skipAbstracts ? "OFF" : "ON"}`);
  console.log(`Full text (methods): ${fetchFullTextContent ? "ON" : "OFF"}`);
  console.log(
    `Test mode: ${testMode ? "ON (using well-known studies)" : "OFF"}`
  );
  console.log(`Study limit: ${limit || "none"}`);
  console.log();

  // Load studies
  let studies = testMode ? TEST_STUDIES : loadStudyIds();
  console.log(
    `Loaded ${studies.length} studies ${testMode ? "(test set)" : "from catalog"}`
  );

  if (limit) {
    studies = studies.slice(0, limit);
    console.log(`Limited to ${studies.length} studies`);
  }

  // Process each study
  const results: StudyPublications[] = [];
  let totalPubs = 0;
  let studiesWithPubs = 0;

  for (let i = 0; i < studies.length; i++) {
    const study = studies[i];
    const progress = `[${i + 1}/${studies.length}]`;

    try {
      const result = await processStudy(
        study.phsId,
        study.studyName,
        fetchFullTextContent,
        skipAbstracts
      );

      results.push(result);
      totalPubs += result.publicationCount;
      if (result.publicationCount > 0) studiesWithPubs++;

      console.log(
        `${progress} ${study.phsId}: ${result.publicationCount} publications`
      );
    } catch (error) {
      console.error(`${progress} ${study.phsId}: ERROR - ${error}`);
      results.push({
        phsId: study.phsId,
        studyName: study.studyName,
        publicationCount: 0,
        publications: [],
        fetchedAt: new Date().toISOString(),
      });
    }

    // Progress update every 10 studies
    if ((i + 1) % 10 === 0) {
      console.log(
        `  ... processed ${i + 1} studies, ${totalPubs} publications found`
      );
    }
  }

  // Build final results
  const pipelineResults: PipelineResults = {
    totalStudies: studies.length,
    totalPublications: totalPubs,
    studiesWithPublications: studiesWithPubs,
    fetchedAt: new Date().toISOString(),
    studies: results.sort((a, b) => b.publicationCount - a.publicationCount),
  };

  // Write output
  const outputPath = path.join(
    __dirname,
    "..",
    "catalog",
    "study-publications.json"
  );
  fs.writeFileSync(outputPath, JSON.stringify(pipelineResults, null, 2));

  console.log();
  console.log("=".repeat(60));
  console.log("Pipeline Complete");
  console.log("=".repeat(60));
  console.log(`Total studies processed: ${pipelineResults.totalStudies}`);
  console.log(
    `Studies with publications: ${pipelineResults.studiesWithPublications}`
  );
  console.log(`Total publications found: ${pipelineResults.totalPublications}`);
  console.log(`Output: ${outputPath}`);
}

// Export for use as module
export {
  searchPMCForStudy,
  fetchPMCMetadata,
  fetchFullText,
  processStudy,
  Publication,
  StudyPublications,
  PipelineResults,
};

// Run if called directly
main().catch(console.error);
