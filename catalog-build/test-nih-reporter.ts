/**
 * Test script for NIH RePORTER API publication discovery
 *
 * Goal: Find publications linked to dbGaP studies via their funding grants
 *
 * Approach:
 * 1. Search RePORTER for projects mentioning the study name or dbGaP accession
 * 2. Get publications linked to those grants
 *
 * API Docs: https://api.reporter.nih.gov/
 */

interface ReporterProject {
  project_num: string;
  project_title: string;
  abstract_text?: string;
  fiscal_year: number;
  organization?: {
    org_name: string;
  };
  principal_investigators?: Array<{
    first_name: string;
    last_name: string;
  }>;
}

interface ReporterPublication {
  pmid: number;
  coreproject: string;
  applid: number;
}

interface ProjectSearchResponse {
  meta: { total: number };
  results: ReporterProject[];
}

interface PublicationSearchResponse {
  meta: { total: number };
  results: ReporterPublication[];
}

const REPORTER_BASE_URL = "https://api.reporter.nih.gov/v2";

/**
 * Search for NIH projects by text query
 */
async function searchProjects(query: string): Promise<ProjectSearchResponse> {
  const response = await fetch(`${REPORTER_BASE_URL}/projects/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria: {
        advanced_text_search: {
          operator: "and",
          search_field: "all",
          search_text: query,
        },
      },
      offset: 0,
      limit: 25,
    }),
  });

  if (!response.ok) {
    throw new Error(`Project search failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Get publications for a specific project number
 */
async function getPublicationsForProject(
  projectNum: string
): Promise<PublicationSearchResponse> {
  const response = await fetch(`${REPORTER_BASE_URL}/publications/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria: {
        core_project_nums: [projectNum],
      },
      offset: 0,
      limit: 50,
    }),
  });

  if (!response.ok) {
    throw new Error(`Publication search failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Search for publications by text (terms in title/abstract)
 */
async function searchPublicationsByText(
  query: string
): Promise<PublicationSearchResponse> {
  const response = await fetch(`${REPORTER_BASE_URL}/publications/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria: {
        advanced_text_search: {
          operator: "and",
          search_field: "all",
          search_text: query,
        },
      },
      offset: 0,
      limit: 25,
    }),
  });

  if (!response.ok) {
    throw new Error(`Publication text search failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Get publications for multiple project numbers
 */
async function getPublicationsForProjects(
  projectNums: string[]
): Promise<PublicationSearchResponse> {
  const response = await fetch(`${REPORTER_BASE_URL}/publications/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria: {
        core_project_nums: projectNums,
      },
      offset: 0,
      limit: 100,
    }),
  });

  if (!response.ok) {
    throw new Error(`Publication search failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Test study - query for projects and publications
 */
async function testStudy(
  studyName: string,
  dbgapId: string
): Promise<void> {
  console.log(`\n${"=".repeat(60)}`);
  console.log(`Testing: ${studyName} (${dbgapId})`);
  console.log("=".repeat(60));

  // Strategy 1: Search by study name
  console.log(`\n[1] Searching projects for: "${studyName}"`);
  const nameResults = await searchProjects(studyName);
  console.log(`   Found ${nameResults.meta.total} projects`);

  if (nameResults.results.length > 0) {
    console.log("   Top 5 projects:");
    for (const proj of nameResults.results.slice(0, 5)) {
      const title = proj.project_title?.slice(0, 50) || "(no title)";
      console.log(`   - ${proj.project_num} (FY${proj.fiscal_year}): ${title}...`);
    }
  }

  // Collect unique core project numbers from results
  const coreProjects = new Set<string>();
  for (const proj of nameResults.results.slice(0, 10)) {
    // Core project is the base without subproject suffixes
    // e.g., "5R01HL123456-02" -> "R01HL123456"
    const match = proj.project_num.match(/[A-Z]\d{2}[A-Z]{2}\d+/);
    if (match) {
      coreProjects.add(match[0]);
    }
  }

  if (coreProjects.size > 0) {
    const coreList = Array.from(coreProjects).slice(0, 5);
    console.log(`\n[2] Getting publications for ${coreList.length} core projects: ${coreList.join(", ")}`);

    const pubs = await getPublicationsForProjects(coreList);
    console.log(`   Found ${pubs.meta.total} publications`);

    if (pubs.results.length > 0) {
      console.log("   Sample PMIDs:", pubs.results.slice(0, 10).map((p) => p.pmid).join(", "));
    }
  }

  // Strategy 3: Direct publication search by study name
  console.log(`\n[3] Direct publication search for: "${studyName}"`);
  const pubsByName = await searchPublicationsByText(studyName);
  console.log(`   Found ${pubsByName.meta.total} publications mentioning study name`);

  if (pubsByName.results.length > 0) {
    console.log("   Sample PMIDs:", pubsByName.results.slice(0, 10).map((p) => p.pmid).join(", "));
  }
}

/**
 * Search for R01-style core grants associated with a study
 * Filter for older grants more likely to have publications
 */
async function searchOlderGrants(studyName: string): Promise<string[]> {
  const response = await fetch(`${REPORTER_BASE_URL}/projects/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      criteria: {
        advanced_text_search: {
          operator: "and",
          search_field: "all",
          search_text: studyName,
        },
        fiscal_years: [2015, 2016, 2017, 2018, 2019, 2020],
      },
      offset: 0,
      limit: 50,
      sort_field: "fiscal_year",
      sort_order: "desc",
    }),
  });

  if (!response.ok) {
    throw new Error(`Grant search failed: ${response.status}`);
  }

  const data = (await response.json()) as ProjectSearchResponse;

  // Extract unique core project numbers
  const coreProjects = new Set<string>();
  for (const proj of data.results) {
    const match = proj.project_num.match(/[A-Z]\d{2}[A-Z]{2}\d+/);
    if (match) {
      coreProjects.add(match[0]);
    }
  }

  return Array.from(coreProjects);
}

/**
 * Get detailed publication info
 */
async function getPublicationDetails(pmids: number[]): Promise<void> {
  // Use NCBI E-utilities to get publication details
  const idsParam = pmids.join(",");
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=${idsParam}&retmode=json`;

  const response = await fetch(url);
  if (!response.ok) {
    console.log("   Could not fetch publication details");
    return;
  }

  const data = await response.json();
  console.log("   Publication titles:");

  for (const pmid of pmids.slice(0, 3)) {
    const pub = data.result?.[pmid.toString()];
    if (pub) {
      const title = pub.title?.slice(0, 70) || "(no title)";
      const year = pub.pubdate?.split(" ")[0] || "????";
      console.log(`   - PMID ${pmid} (${year}): ${title}...`);
    }
  }
}

/**
 * Deep test for a single study with verification
 */
async function deepTestStudy(studyName: string, dbgapId: string): Promise<void> {
  console.log(`\n${"=".repeat(60)}`);
  console.log(`DEEP TEST: ${studyName} (${dbgapId})`);
  console.log("=".repeat(60));

  // Get grants from 2015-2020 (more likely to have publications)
  console.log("\n[1] Searching for older grants (2015-2020)...");
  const olderGrants = await searchOlderGrants(studyName);
  console.log(`   Found ${olderGrants.length} unique core grants`);

  if (olderGrants.length > 0) {
    console.log(`   Grants: ${olderGrants.slice(0, 10).join(", ")}`);

    // Get publications for these grants
    console.log("\n[2] Getting publications for these grants...");
    const pubs = await getPublicationsForProjects(olderGrants.slice(0, 10));
    console.log(`   Found ${pubs.meta.total} total publications`);

    if (pubs.results.length > 0) {
      const pmids = pubs.results.slice(0, 5).map((p) => p.pmid);
      console.log(`   Sample PMIDs: ${pmids.join(", ")}`);

      // Verify these are real and get titles
      console.log("\n[3] Verifying publication details...");
      await getPublicationDetails(pmids);
    }
  }
}

/**
 * Search PubMed/PMC for papers citing a dbGaP accession
 */
async function searchPubMedForDbGap(dbgapId: string): Promise<void> {
  console.log(`\n[PubMed] Searching for "${dbgapId}" in full text...`);

  // Search PMC (open access full text)
  const searchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term=${dbgapId}&retmode=json&retmax=100`;

  const response = await fetch(searchUrl);
  if (!response.ok) {
    console.log("   PMC search failed");
    return;
  }

  const data = await response.json();
  const count = data.esearchresult?.count || 0;
  const ids = data.esearchresult?.idlist || [];

  console.log(`   Found ${count} PMC articles citing ${dbgapId}`);

  if (ids.length > 0) {
    // Get article details
    const idsParam = ids.slice(0, 5).join(",");
    const detailUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id=${idsParam}&retmode=json`;

    const detailResp = await fetch(detailUrl);
    if (detailResp.ok) {
      const details = await detailResp.json();
      console.log("   Sample articles:");

      for (const id of ids.slice(0, 3)) {
        const article = details.result?.[id];
        if (article) {
          const title = article.title?.slice(0, 65) || "(no title)";
          const year = article.pubdate?.split(" ")[0] || "????";
          console.log(`   - PMC${id} (${year}): ${title}...`);
        }
      }
    }
  }

  // Also search PubMed (abstracts only, but broader coverage)
  await new Promise((resolve) => setTimeout(resolve, 350));
  const pubmedUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${dbgapId}&retmode=json&retmax=10`;

  const pubmedResp = await fetch(pubmedUrl);
  if (pubmedResp.ok) {
    const pubmedData = await pubmedResp.json();
    console.log(`   Also found ${pubmedData.esearchresult?.count || 0} PubMed abstracts mentioning ${dbgapId}`);
  }
}

/**
 * Main - test on a few well-known dbGaP studies
 */
async function main(): Promise<void> {
  console.log("NIH RePORTER Publication Discovery Test");
  console.log("API: https://api.reporter.nih.gov/v2\n");

  // Test approach 1: Grant-based discovery
  console.log("=" .repeat(60));
  console.log("APPROACH 1: Grant-based discovery (NIH RePORTER)");
  console.log("Finds papers from grants that mention the study");
  console.log("=".repeat(60));

  await deepTestStudy("Framingham Heart Study", "phs000007");
  await new Promise((resolve) => setTimeout(resolve, 500));

  // Test approach 2: Direct citation search
  console.log("\n\n" + "=".repeat(60));
  console.log("APPROACH 2: Direct citation search (PubMed/PMC)");
  console.log("Finds papers that cite the dbGaP accession number");
  console.log("=".repeat(60));

  await searchPubMedForDbGap("phs000007");
  await new Promise((resolve) => setTimeout(resolve, 500));
  await searchPubMedForDbGap("phs000286");
  await new Promise((resolve) => setTimeout(resolve, 500));
  await searchPubMedForDbGap("phs000209");

  console.log("\n\n" + "=".repeat(60));
  console.log("SUMMARY:");
  console.log("=".repeat(60));
  console.log(`
Approach 1 (Grant-based):
  ✓ Finds many publications (~hundreds to thousands)
  ✗ Papers are from grants that MENTION the study, not necessarily
    papers ABOUT the study or using its data
  ✗ Low precision - many false positives

Approach 2 (Direct citation):
  ✓ High precision - papers that explicitly cite the dbGaP ID
  ✗ Lower recall - not all papers cite the accession number
  ✓ Good for secondary analyses that properly cite data source

Recommendation: Use Approach 2 for high-quality links, potentially
supplement with Approach 1 for major studies with known core grants.
`);
}

main().catch(console.error);
