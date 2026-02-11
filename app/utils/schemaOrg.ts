import { Publication } from "../apis/catalog/common/entities";
import { NCPICatalogStudy } from "../apis/catalog/ncpi-catalog/common/entities";
import { stripHtmlTags } from "./htmlUtils";

/**
 * Maximum number of publications to include in the JSON-LD citation array.
 */
const MAX_CITATIONS = 5;

/**
 * Maximum description length per Google Dataset Search guidelines.
 */
const MAX_DESCRIPTION_LENGTH = 5000;

/**
 * Base URL for dbGaP study pages.
 */
const DBGAP_STUDY_URL =
  "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=";

/**
 * Schema.org DataDownload type.
 */
interface SchemaDataDownload {
  "@type": "DataDownload";
  contentUrl: string;
}

/**
 * Schema.org DataCatalog type.
 */
interface SchemaDataCatalog {
  "@type": "DataCatalog";
  name: string;
  url: string;
}

/**
 * Schema.org Person type.
 */
interface SchemaPerson {
  "@type": "Person";
  name: string;
}

/**
 * Schema.org ScholarlyArticle type.
 */
interface SchemaScholarlyArticle {
  "@type": "ScholarlyArticle";
  author?: SchemaPerson[];
  headline: string;
  name: string;
  sameAs?: string;
}

/**
 * Schema.org Dataset JSON-LD structure.
 */
export interface SchemaDataset {
  "@context": "https://schema.org";
  "@type": "Dataset";
  citation?: SchemaScholarlyArticle[];
  description: string;
  distribution?: SchemaDataDownload[];
  identifier: string[];
  includedInDataCatalog: SchemaDataCatalog;
  isAccessibleForFree: boolean;
  keywords?: string[];
  measurementTechnique?: string[];
  name: string;
  sameAs?: string;
  url: string;
  version?: string;
}

/**
 * Builds a Schema.org Dataset JSON-LD object from a study.
 * @param study - The NCPI catalog study.
 * @param browserURL - The base URL of the site.
 * @returns Schema.org Dataset JSON-LD object.
 */
export function buildStudyJsonLd(
  study: NCPICatalogStudy,
  browserURL: string
): SchemaDataset {
  const dbGapStudyUrl = `${DBGAP_STUDY_URL}${study.studyAccession}`;
  const jsonLd: SchemaDataset = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    description: truncateDescription(stripHtmlTags(study.studyDescription)),
    identifier: [study.dbGapId, study.studyAccession],
    includedInDataCatalog: {
      "@type": "DataCatalog",
      name: "NCPI Dataset Catalog",
      url: browserURL,
    },
    isAccessibleForFree: false,
    name: study.title,
    sameAs: dbGapStudyUrl,
    url: `${browserURL}/studies/${study.dbGapId}`,
  };

  const keywords = buildKeywords(study.focus, study.studyDesign);
  if (keywords.length > 0) {
    jsonLd.keywords = keywords;
  }

  const dataTypes = study.dataType.filter((dt) => dt !== "Unspecified");
  if (dataTypes.length > 0) {
    jsonLd.measurementTechnique = dataTypes;
  }

  const version = parseVersion(study.studyAccession);
  if (version) {
    jsonLd.version = version;
  }

  if (study.studyAccession) {
    jsonLd.distribution = [
      {
        "@type": "DataDownload",
        contentUrl: dbGapStudyUrl,
      },
    ];
  }

  const citations = buildCitations(study.publications);
  if (citations.length > 0) {
    jsonLd.citation = citations;
  }

  return jsonLd;
}

/**
 * Builds the keywords array from focus and study design.
 * @param focus - Study focus/disease area.
 * @param studyDesign - Array of study designs.
 * @returns Combined keywords array.
 */
function buildKeywords(focus: string, studyDesign: string[]): string[] {
  const keywords: string[] = [];
  if (focus) {
    keywords.push(focus);
  }
  for (const design of studyDesign) {
    if (design) {
      keywords.push(design);
    }
  }
  return keywords;
}

/**
 * Builds Schema.org ScholarlyArticle citations from publications.
 * @param publications - Array of publications.
 * @returns Array of ScholarlyArticle objects, limited to top citations.
 */
function buildCitations(publications: Publication[]): SchemaScholarlyArticle[] {
  return [...publications]
    .sort((a, b) => b.citationCount - a.citationCount)
    .slice(0, MAX_CITATIONS)
    .map(buildScholarlyArticle);
}

/**
 * Parses a comma-separated author string into Schema.org Person objects.
 * @param authors - Comma-separated author string (e.g. "A. Smith, B. Jones, et al.").
 * @returns Array of Person objects.
 */
function parseAuthors(authors: string): SchemaPerson[] {
  if (!authors) return [];
  return authors
    .split(", ")
    .map((name) => name.trim())
    .filter((name) => name && name.toLowerCase() !== "et al.")
    .map((name) => ({ "@type": "Person" as const, name }));
}

/**
 * Truncates a description to the Google Dataset Search maximum of 5000 characters.
 * @param description - Plain text description.
 * @returns Truncated description.
 */
function truncateDescription(description: string): string {
  if (description.length <= MAX_DESCRIPTION_LENGTH) return description;
  return description.slice(0, MAX_DESCRIPTION_LENGTH - 1) + "\u2026";
}

/**
 * Parses the version number from a dbGaP study accession string.
 * @param studyAccession - Study accession (e.g. "phs000209.v13.p3").
 * @returns Version string (e.g. "13"), or undefined if not parseable.
 */
function parseVersion(studyAccession: string): string | undefined {
  const match = studyAccession.match(/\.v(\d+)\./);
  return match?.[1];
}

/**
 * Builds a single ScholarlyArticle from a publication.
 * @param publication - The publication to convert.
 * @returns ScholarlyArticle object.
 */
function buildScholarlyArticle(
  publication: Publication
): SchemaScholarlyArticle {
  const article: SchemaScholarlyArticle = {
    "@type": "ScholarlyArticle",
    headline: publication.title,
    name: publication.title,
  };
  const authors = parseAuthors(publication.authors);
  if (authors.length > 0) {
    article.author = authors;
  }
  if (publication.doi) {
    article.sameAs = `https://doi.org/${publication.doi}`;
  }
  return article;
}
