import { Publication } from "../../../../apis/catalog/common/entities";

/**
 * Formats a citation string from a publication's authors, year, and journal.
 * @param publication - Publication to format.
 * @returns Formatted citation string.
 */
export function formatCitation(
  publication: Pick<Publication, "authors" | "journal" | "year">
): string {
  const parts: string[] = [];
  if (publication.authors) {
    parts.push(`${publication.authors}.`);
  }
  if (publication.year) {
    parts.push(`(${publication.year}).`);
  }
  if (publication.journal) {
    parts.push(`${publication.journal}.`);
  }
  return parts.join(" ");
}

/**
 * Returns a DOI URL from a DOI string.
 * @param doi - DOI identifier.
 * @returns Full DOI URL.
 */
export function getDOIUrl(doi: string): string {
  return `https://doi.org/${doi}`;
}
