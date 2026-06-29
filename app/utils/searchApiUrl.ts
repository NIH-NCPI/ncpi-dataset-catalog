/**
 * Returns the search API URL, preferring the env var over the site config value.
 *
 * The resolved base URL targets the deterministic `/search` endpoint. Pass
 * `{ agent: true }` to target the agentic `/search/agent` endpoint instead
 * (used by the `?agent=1` URL flag); the base URL ends in `/search`, so the
 * agent URL is simply that with `/agent` appended.
 * @param configUrl - The URL from site config (`config.ai?.url`).
 * @param options - Resolution options.
 * @param options.agent - When true, return the `/search/agent` URL.
 * @returns Resolved search API URL, or empty string if neither is set.
 */
export function getSearchApiUrl(
  configUrl?: string,
  options?: { agent?: boolean }
): string {
  const base = process.env.NEXT_PUBLIC_SEARCH_API_URL || configUrl || "";
  if (!base) return "";
  return options?.agent ? `${base}/agent` : base;
}
