import { ParsedUrlQuery } from "querystring";

/**
 * Build a new query object for the given tab, preserving the entityListType and entityId from the given query.
 * @param query - Query.
 * @param tab - Tab value.
 * @returns New query object with updated tab value.
 */
export function buildNextQuery(
  query: ParsedUrlQuery,
  tab: string
): ParsedUrlQuery {
  const { entityListType, params } = query;

  if (!entityListType || !params || typeof params === "string")
    throw new Error("Unexpected query params", { cause: { query } });

  const [entityId] = params;

  return { entityListType, params: [entityId, tab] };
}

/**
 * Get the current tab value from the query.
 * @param query - Query.
 * @returns Tab value.
 */
export function getTabValue(query: ParsedUrlQuery): string {
  const { params } = query;

  if (!params || typeof params === "string")
    throw new Error("Unexpected query params", { cause: { query } });

  // Handle case where params is an array but has no value at index 1 e.g. "overview" tab where params is [entityId] instead of [entityId, "overview"].
  const [, value = ""] = params;

  return value;
}
