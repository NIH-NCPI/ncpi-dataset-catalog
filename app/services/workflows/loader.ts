import { API } from "./routes";
import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { getEntitiesById, setEntitiesById, setEntitiesByType } from "./store";
import { EntityRoute } from "./types";

/**
 * Fetches entities from the API.
 * @param url - URL.
 * @returns Entity list.
 */
async function fetchEntities(url: string): Promise<unknown[]> {
  const res = await fetch(url);

  if (!res.ok) throw new Error(`Failed to fetch: ${url}`);

  const data = (await res.json()) as unknown[];

  if (!Array.isArray(data)) {
    return Object.values(data);
  }

  return data;
}

/**
 * Checks if the route is an entity route.
 * @param route - Route.
 * @returns True if the route is an entity route; false otherwise.
 */
function isEntityRoute(route: string): route is EntityRoute {
  return route in API;
}

/**
 * Loads the entities store with entities from the API.
 * @param config - Site config.
 */
export async function loadEntities(config: SiteConfig): Promise<void> {
  for (const entity of config.entities) {
    const { entityMapper, getId, route } = entity;

    if (!isEntityRoute(route)) continue;

    const apiRoute = API[route];

    // Entities are already loaded; skip.
    if (getEntitiesById().has(route)) continue;

    // Get id function is not configured; entities are excluded from preloading.
    if (!getId) continue;

    // Fetch the entities.
    const rawEntities = await fetchEntities(apiRoute);

    // Apply mapper if provided
    const entities = entityMapper ? rawEntities.map(entityMapper) : rawEntities;

    const entityById = new Map<string, unknown>();
    for (const entity of entities) entityById.set(getId(entity), entity);

    setEntitiesById(route, entityById);
    setEntitiesByType(route, entities);
  }
}
