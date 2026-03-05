/**
 * Returns the search API URL, preferring the env var over the site config value.
 * @param configUrl - The URL from site config (`config.ai?.url`).
 * @returns Resolved search API URL, or empty string if neither is set.
 */
export function getSearchApiUrl(configUrl?: string): string {
  return process.env.NEXT_PUBLIC_SEARCH_API_URL || configUrl || "";
}
