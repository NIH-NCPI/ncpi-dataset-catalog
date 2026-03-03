import { NCPICatalogStudy } from "../../apis/catalog/ncpi-catalog/common/entities";
import { getEntities, getEntity } from "./query";

/**
 * Gets studies.
 * @returns Studies.
 */
export function getStudies<T extends NCPICatalogStudy>(): T[] {
  return getEntities<T>("studies");
}

/**
 * Gets study by entity id.
 * @param entityId - Entity id.
 * @returns Study.
 */
export function getStudy<T extends NCPICatalogStudy>(entityId: string): T {
  return getEntity<T>("studies", entityId);
}
