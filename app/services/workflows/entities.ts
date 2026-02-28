import { getEntities, getEntity } from "./query";
import { Study } from "../../views/ResearchView/ui/Datasets/types/study";

/**
 * Gets studies.
 * @returns Studies.
 */
export function getStudies<T extends Study>(): T[] {
  return getEntities<T>("studies");
}

/**
 * Gets study by entity id.
 * @param entityId - Entity id.
 * @returns Study.
 */
export function getStudy<T extends Study>(entityId: string): T {
  return getEntity<T>("studies", entityId);
}
