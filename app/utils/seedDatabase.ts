import { EntityConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { database } from "@databiosphere/findable-ui/lib/utils/database";
import fsp from "fs/promises";
import path from "path";

/**
 * Parsed-and-mapped entities per route, memoized for the lifetime of the
 * build worker. Reading, parsing and mapping the static-load file is
 * expensive (ncpi-platform-studies.json is ~24 MB and getStaticProps runs
 * once per prerendered page), so it happens once per route here and every
 * build-time consumer reads from this cache.
 */
const entitiesByRoute = new Map<string, unknown[]>();

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
 * @param entityConfig - Entity config.
 * @param entityId - Entity id.
 * @returns Entity with the given id, or undefined when not found.
 */
export async function getBuildTimeEntity(
  entityConfig: EntityConfig,
  entityId: string
): Promise<unknown> {
  const { getId, label, route } = entityConfig;
  let entityById = entityByIdByRoute.get(route);
  if (!entityById) {
    if (!getId) throw new Error(`No getId function for ${label}`);
    const entities = await loadEntities(entityConfig);
    entityById = new Map(entities.map((entity) => [getId(entity), entity]));
    entityByIdByRoute.set(route, entityById);
  }
  return entityById.get(entityId);
}

/**
 * Reads, parses and maps the entity config's static-load file, memoized per
 * route for the lifetime of the build worker.
 * @param entityConfig - Entity config.
 * @returns Entities from the static-load file.
 */
async function loadEntities(entityConfig: EntityConfig): Promise<unknown[]> {
  const { entityMapper, label, route, staticLoadFile } = entityConfig;

  if (!staticLoadFile) throw new Error(`No static file for ${label}`);

  let entities = entitiesByRoute.get(route);
  if (entities) return entities;

  // Read file.
  const filePath = path.resolve(process.cwd(), staticLoadFile);
  let fileContent;
  try {
    fileContent = await fsp.readFile(filePath, "utf8");
  } catch {
    throw new Error(`File not found: ${staticLoadFile}`);
  }

  // Parse file content.
  const object = JSON.parse(fileContent);

  // Map entities.
  entities = entityMapper
    ? Object.values(object).map(entityMapper)
    : Object.values(object);

  entitiesByRoute.set(route, entities);
  return entities;
}

/**
 * Seed database. Required only where findable-ui's TSV entity service is the
 * reader (CS_FETCH_CS_FILTERING detail fetches go through the service, which
 * reads this database internally); our own build-time code reads the memoized
 * cache via getBuildTimeEntities/getBuildTimeEntity instead. The seed write
 * runs on every call — other build-time code (the local seedDatabase in
 * pages/[entityListType]/index.tsx) seeds the same routes with UNMAPPED
 * entities and build workers interleave pages, so a "skip if already seeded"
 * guard could leave the wrong shape in the database.
 * @param entityConfig - Entity config.
 */
export async function seedDatabase(entityConfig: EntityConfig): Promise<void> {
  database.get().seed(entityConfig.route, await loadEntities(entityConfig));
}
