/**
 * Returns the search API URL, preferring the env var over the site config value.
 * Returned verbatim (no validation or normalization). By convention the value
 * ends in `/search`, which callers rely on: the form posts to it directly (and
 * appends `/filter` for chip removal), and `Status` swaps the `/search` suffix
 * for `/health`.
 * @param configUrl - The URL from site config (`config.ai?.url`).
 * @returns Resolved search API URL, or empty string if neither is set.
 */
export function getSearchApiUrl(configUrl?: string): string {
  return process.env.NEXT_PUBLIC_SEARCH_API_URL || configUrl || "";
}
