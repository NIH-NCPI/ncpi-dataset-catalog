import { EntityConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { database } from "@databiosphere/findable-ui/lib/utils/database";
import fsp from "fs/promises";

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
 * Seed database.
 * @param entityConfig - Entity config.
 */
export async function seedDatabase(entityConfig: EntityConfig): Promise<void> {
  const { entityMapper, label, route, staticLoadFile } = entityConfig;

  if (!staticLoadFile) throw new Error(`No static file for ${label}`);

  let fileContent;

  // Read file.
  try {
    fileContent = await fsp.readFile(staticLoadFile, "utf8");
  } catch {
    throw new Error(`File not found: ${staticLoadFile}`);
  }

  // Parse file content.
  const object = JSON.parse(fileContent);

  // Map entities.
  const entities = entityMapper
    ? Object.values(object).map(entityMapper)
    : Object.values(object);

  // Seed database.
  database.get().seed(route, entities);
}
