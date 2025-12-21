/**
 * FHIR-first data fetching module for dbGaP studies.
 * Pages through all ResearchStudy resources from the dbGaP FHIR API.
 */

import fetch from "node-fetch";
import { decode } from "html-entities";

const FHIR_BASE = "https://dbgap-api.ncbi.nlm.nih.gov/fhir/x1";
const PAGE_SIZE = 100;
const API_DELAY = 350;

/**
 * Study data extracted from FHIR.
 */
export interface FHIRStudyData {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  description: string;
  focus: string;
  participantCount: number;
  studyAccession: string;
  studyDesigns: string[];
  title: string;
}

/**
 * Delays execution for rate limiting.
 * @param ms - Milliseconds to delay.
 * @returns Promise that resolves after the delay.
 */
async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * FHIR Extension type (simplified).
 */
interface FHIRExtension {
  extension?: FHIRExtension[];
  url?: string;
  valueCodeableConcept?: { coding?: Array<{ code?: string }> };
  valueCoding?: { code?: string; display?: string };
  valueCount?: { value?: number };
  valueInteger?: number;
  valueString?: string;
}

/**
 * FHIR ResearchStudy resource (simplified).
 */
interface FHIRResearchStudy {
  category?: Array<{
    coding?: Array<{ code?: string; system?: string }>;
  }>;
  description?: string;
  extension?: FHIRExtension[];
  focus?: Array<{ text?: string }>;
  id?: string;
  identifier?: Array<{ value?: string }>;
  title?: string;
}

/**
 * FHIR Bundle response.
 */
interface FHIRBundle {
  entry?: Array<{ resource?: FHIRResearchStudy }>;
  link?: Array<{ relation?: string; url?: string }>;
  total?: number;
}

/**
 * Finds an extension by type suffix.
 * @param extensions - Array of FHIR extensions to search.
 * @param typeSuffix - Suffix to match in extension URL.
 * @returns The matching extension or undefined.
 */
function findExtension(
  extensions: FHIRExtension[] | undefined,
  typeSuffix: string
): FHIRExtension | undefined {
  if (!extensions) return undefined;
  return extensions.find((ext) =>
    ext.url?.toLowerCase().includes(typeSuffix.toLowerCase())
  );
}

/**
 * Extracts participant count from FHIR extensions.
 * @param resource - FHIR ResearchStudy resource.
 * @returns Participant count or 0.
 */
function extractParticipantCount(resource: FHIRResearchStudy): number {
  const contentExt = findExtension(resource.extension, "ResearchStudy-Content");
  if (!contentExt?.extension) return 0;

  const numSubjectsExt = findExtension(contentExt.extension, "NumSubjects");
  return numSubjectsExt?.valueCount?.value || 0;
}

/**
 * Extracts consent codes from FHIR extensions.
 * @param resource - FHIR ResearchStudy resource.
 * @returns Array of consent code strings.
 */
function extractConsentCodes(resource: FHIRResearchStudy): string[] {
  const consentsExt = findExtension(
    resource.extension,
    "ResearchStudy-StudyConsents"
  );
  if (!consentsExt?.extension) return [];

  const codes: string[] = [];
  for (const ext of consentsExt.extension) {
    const display = ext.valueCoding?.display;
    if (display) {
      codes.push(display);
    }
  }
  return codes;
}

/**
 * Extracts molecular data types from FHIR extensions.
 * @param resource - FHIR ResearchStudy resource.
 * @returns Array of data type strings.
 */
function extractDataTypes(resource: FHIRResearchStudy): string[] {
  const dataTypesExt = findExtension(resource.extension, "MolecularDataTypes");
  if (!dataTypesExt?.extension) return [];

  const types: string[] = [];
  for (const ext of dataTypesExt.extension) {
    const coding = ext.valueCodeableConcept?.coding;
    if (coding) {
      for (const c of coding) {
        if (c.code) {
          types.push(c.code);
        }
      }
    }
  }
  return [...new Set(types)].sort();
}

/**
 * Extracts study designs from FHIR category.
 * @param resource - FHIR ResearchStudy resource.
 * @returns Array of study design strings.
 */
function extractStudyDesigns(resource: FHIRResearchStudy): string[] {
  const designs: string[] = [];
  const categories = resource.category || [];

  for (const cat of categories) {
    const coding = cat.coding || [];
    for (const c of coding) {
      if (c.system?.includes("StudyDesign") && c.code) {
        designs.push(c.code);
      }
    }
  }
  return [...new Set(designs)];
}

/**
 * Parses a single FHIR resource into our study format.
 * @param resource - FHIR ResearchStudy resource.
 * @returns Parsed study data or null if invalid.
 */
function parseResource(resource: FHIRResearchStudy): FHIRStudyData | null {
  if (!resource.id) return null;

  const title = resource.title ? decode(resource.title) : "";
  if (!title) return null;

  return {
    consentCodes: extractConsentCodes(resource),
    dataTypes: extractDataTypes(resource),
    dbGapId: resource.id,
    description: resource.description || "",
    focus: resource.focus?.[0]?.text || "",
    participantCount: extractParticipantCount(resource),
    studyAccession: resource.identifier?.[0]?.value || resource.id,
    studyDesigns: extractStudyDesigns(resource),
    title,
  };
}

/**
 * Result from fetching a page of studies.
 */
interface FetchPageResult {
  nextUrl: string | null;
  studies: FHIRStudyData[];
  total: number;
}

/**
 * Fetches a single page of studies from FHIR.
 * @param offset - Offset for pagination.
 * @returns Page result with studies, next URL, and total count.
 */
async function fetchPage(offset: number): Promise<FetchPageResult> {
  const url = `${FHIR_BASE}/ResearchStudy?_count=${PAGE_SIZE}&_offset=${offset}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`FHIR fetch failed: ${response.status}`);
  }

  const bundle = (await response.json()) as FHIRBundle;
  const studies: FHIRStudyData[] = [];

  for (const entry of bundle.entry || []) {
    if (entry.resource) {
      const study = parseResource(entry.resource);
      if (study) {
        studies.push(study);
      }
    }
  }

  const nextLink = bundle.link?.find((l) => l.relation === "next");

  return {
    nextUrl: nextLink?.url || null,
    studies,
    total: bundle.total || 0,
  };
}

/**
 * Fetches all studies from FHIR by paging through results.
 * @param onProgress - Optional callback for progress updates.
 * @returns Array of all studies.
 */
export async function fetchAllFHIRStudies(
  onProgress?: (fetched: number, total: number) => void
): Promise<FHIRStudyData[]> {
  const allStudies: FHIRStudyData[] = [];
  let offset = 0;
  let total = 0;
  let loggedTotal = false;

  console.log("Fetching studies from FHIR API...");

  let hasMore = true;
  while (hasMore) {
    const result = await fetchPage(offset);
    allStudies.push(...result.studies);

    if (result.total > 0) {
      total = result.total;
      if (!loggedTotal) {
        console.log(`  Total studies in FHIR: ${total}`);
        loggedTotal = true;
      }
    }

    if (onProgress) {
      onProgress(allStudies.length, total);
    }

    const totalStr = total ? "/" + String(total) : "";
    if (allStudies.length % 500 === 0 || !result.nextUrl) {
      console.log(`  Fetched: ${allStudies.length}${totalStr}`);
    }

    if (!result.nextUrl || result.studies.length === 0) {
      hasMore = false;
    } else {
      offset += PAGE_SIZE;
      await delay(API_DELAY);
    }
  }

  console.log(`  Complete: ${allStudies.length} studies fetched`);
  return allStudies;
}

/**
 * Fetches a single study by ID from FHIR.
 * @param phsId - The phs ID to fetch.
 * @returns Study data or null if not found.
 */
export async function fetchFHIRStudy(
  phsId: string
): Promise<FHIRStudyData | null> {
  try {
    const url = `${FHIR_BASE}/ResearchStudy?_id=${phsId}`;
    const response = await fetch(url);

    if (!response.ok) return null;

    const bundle = (await response.json()) as FHIRBundle;
    const entry = bundle.entry?.[0];

    if (!entry?.resource) return null;

    return parseResource(entry.resource);
  } catch {
    return null;
  }
}

/**
 * Generates the dbGaP study page URL.
 * @param studyAccession - Study accession ID.
 * @returns URL to dbGaP study page.
 */
export function getDbGapUrl(studyAccession: string): string {
  return `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=${studyAccession}`;
}
