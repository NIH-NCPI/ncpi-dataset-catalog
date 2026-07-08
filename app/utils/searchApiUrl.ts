/**
 * Returns the base search API URL, preferring the env var over the site config
 * value. The resolved URL ends in `/search`; the agent endpoint is that with
 * `/agent` appended, and the health endpoint (see `Status`) replaces the
 * `/search` suffix with `/health`.
 * @param configUrl - The URL from site config (`config.ai?.url`).
 * @returns Resolved base search API URL, or empty string if neither is set.
 */
export function getSearchApiUrl(configUrl?: string): string {
  return process.env.NEXT_PUBLIC_SEARCH_API_URL || configUrl || "";
}
