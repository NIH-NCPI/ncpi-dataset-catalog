/**
 * Strips HTML tags from a string, returning plain text.
 * @param html - HTML string to strip tags from.
 * @returns Plain text with HTML tags removed.
 */
export function stripHtmlTags(html: string): string {
  return html
    .replace(/<[^>]*>/g, "") //eslint-disable-line sonarjs/slow-regex -- trusted build-time HTML; input is not user-provided
    .replace(/\s+/g, " ")
    .trim();
}
