import { EntityConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { database } from "@databiosphere/findable-ui/lib/utils/database";
import fsp from "fs/promises";
import path from "path";

/**
 * Parsed-and-mapped entities per route, memoized for the lifetime of the
 * build worker. Reading, parsing and mapping the static-load file is the
 * expensive part of seeding (ncpi-platform-studies.json is ~24 MB and
 * getStaticProps invokes seedDatabase once per prerendered page); the seed
 * write itself stays unconditional — see seedDatabase.
 */
const entitiesByRoute = new Map<string, unknown[]>();

/**
 * Returns all entities for the given entity config at build time, seeding the
 * in-memory database from the config's static-load file. Build-time code must
 * read entities this way rather than through the entity service: with
 * SS_FETCH_CS_FILTERING (apiPath set) the service resolves to API_CF, whose
 * fetchAllEntities issues an HTTP request for the relative apiPath — which
 * cannot work at build time.
 * @param entityConfig - Entity config.
 * @returns Entities from the seeded database.
 */
export async function getBuildTimeEntities(
  entityConfig: EntityConfig
): Promise<unknown[]> {
  await seedDatabase(entityConfig);
  return database.get().all(entityConfig.route);
}

/**
 * Seed database. The file read/parse/map is memoized per route, but the seed
 * write runs on EVERY call: other build-time code (the local seedDatabase in
 * pages/[entityListType]/index.tsx) seeds the same routes with UNMAPPED
 * entities, and build workers interleave pages — skipping the write when the
 * route "is already seeded" could leave the wrong shape in the database.
 * @param entityConfig - Entity config.
 */
export async function seedDatabase(entityConfig: EntityConfig): Promise<void> {
  const { entityMapper, label, route, staticLoadFile } = entityConfig;

  if (!staticLoadFile) throw new Error(`No static file for ${label}`);

  let entities = entitiesByRoute.get(route);

  if (!entities) {
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
  }

  // Seed database.
  database.get().seed(route, entities);
}
