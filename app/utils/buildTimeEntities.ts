import type { EntityConfig } from "@databiosphere/findable-ui/lib/config/entities";
import fsp from "fs/promises";
import path from "path";

/**
 * Promises of parsed-and-mapped entities per route, memoized for the lifetime
 * of the build worker. Reading, parsing and mapping the static-load file is
 * expensive (ncpi-platform-studies.json is ~24 MB and getStaticProps runs
 * once per prerendered page), so it happens once per route here and every
 * build-time reader in this module reads from this cache.
 *
 * Database seeding is separate: it goes through findable-ui's seedDatabase,
 * whose memoized entities are private, so a route that is both seeded and
 * read here is parsed once by each. Studies, the large catalog, are only ever
 * read here and never seeded, so they are still parsed once per worker.
 */
const entitiesByRoute = new Map<string, Promise<unknown[]>>();

/**
 * Entity-by-id indexes per route, derived lazily from entitiesByRoute.
 */
const entityByIdByRoute = new Map<string, Map<string, unknown>>();

/**
 * Returns all entities for the given entity config at build time, loaded from
 * the config's static-load file. Build-time code must read entities this way
 * rather than through the entity service: with SS_FETCH_CS_FILTERING
 * (apiPath set) the service resolves to API_CF, whose fetchAllEntities issues
 * an HTTP request for the relative apiPath — which cannot work at build time.
 * @param entityConfig - Entity config.
 * @returns Entities from the static-load file.
 */
export async function getBuildTimeEntities(
  entityConfig: EntityConfig
): Promise<unknown[]> {
  return loadEntities(entityConfig);
}

/**
 * Returns the entity with the given id for the given entity config at build
 * time, loaded from the config's static-load file — see getBuildTimeEntities.
 * The type parameter is caller-asserted, as with the entity service readers.
 * @param entityConfig - Entity config.
 * @param entityId - Entity id.
 * @returns Entity with the given id, or undefined when not found.
 */
export async function getBuildTimeEntity<T = unknown>(
  entityConfig: EntityConfig,
  entityId: string
): Promise<T | undefined> {
  const { getId, label, route } = entityConfig;
  let entityById = entityByIdByRoute.get(route);
  if (!entityById) {
    if (!getId) throw new Error(`No getId function for ${label}`);
    const entities = await loadEntities(entityConfig);
    entityById = new Map(entities.map((entity) => [getId(entity), entity]));
    entityByIdByRoute.set(route, entityById);
  }
  return entityById.get(entityId) as T | undefined;
}

/**
 * Returns the entities for the entity config's route, memoized per route for
 * the lifetime of the build worker. The in-flight promise is cached, so pages
 * prerendered concurrently share one read, parse and map rather than each
 * starting their own. A failed load is evicted so a later call retries.
 * @param entityConfig - Entity config.
 * @returns Entities from the static-load file.
 */
function loadEntities(entityConfig: EntityConfig): Promise<unknown[]> {
  const { route } = entityConfig;
  let entities = entitiesByRoute.get(route);
  if (!entities) {
    entities = readEntities(entityConfig).catch((error) => {
      entitiesByRoute.delete(route);
      throw error;
    });
    entitiesByRoute.set(route, entities);
  }
  return entities;
}

/**
 * Reads, parses and maps the entity config's static-load file.
 * @param entityConfig - Entity config.
 * @returns Entities from the static-load file.
 */
async function readEntities(entityConfig: EntityConfig): Promise<unknown[]> {
  const { entityMapper, label, staticLoadFile } = entityConfig;

  if (!staticLoadFile) throw new Error(`No static file for ${label}`);

  // Read file.
  const filePath = path.resolve(process.cwd(), staticLoadFile);
  let fileContent;
  try {
    fileContent = await fsp.readFile(filePath, "utf8");
  } catch (error) {
    throw new Error(`Failed to read file ${staticLoadFile} for ${label}`, {
      cause: error,
    });
  }

  // Parse file content.
  let object;
  try {
    object = JSON.parse(fileContent);
  } catch (error) {
    throw new Error(`Failed to parse file ${staticLoadFile} for ${label}`, {
      cause: error,
    });
  }

  // Map entities.
  return entityMapper
    ? Object.values(object).map(entityMapper)
    : Object.values(object);
}
