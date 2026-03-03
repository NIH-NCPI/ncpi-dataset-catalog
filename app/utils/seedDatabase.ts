import fsp from "fs/promises";
import { EntityConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { database } from "@databiosphere/findable-ui/lib/utils/database";

/**
 * Seed database.
 * @param entityListType - Entity list type.
 * @param entityConfig - Entity config.
 */
export async function seedDatabase(
  entityListType: string,
  entityConfig: EntityConfig
): Promise<void> {
  const { entityMapper, label, staticLoadFile } = entityConfig;

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
  database.get().seed(entityListType, entities);
}
