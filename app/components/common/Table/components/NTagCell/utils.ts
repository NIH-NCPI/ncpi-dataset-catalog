import { ComponentProps, JSX } from "react";
import { CellContext, RowData } from "@tanstack/react-table";
import * as C from "../../../../index";
import { METADATA_KEY } from "./../../../../Index/common/entities";
import { getPluralizedMetadataLabel } from "./../../../../Index/common/indexTransformer";

/**
 * Builds props for NTagCell component.
 * @param metadataKey - Metadata key to get label for NTagCell component.
 * @param entityKey - Key of the entity to get values for NTagCell component.
 * @returns Props for NTagCell component.
 */
export const buildNTagProps = <T extends RowData>(
  metadataKey: METADATA_KEY,
  entityKey: keyof T
): ((entity: T) => ComponentProps<typeof C.NTagCell>) => {
  return (entity): ComponentProps<typeof C.NTagCell> => {
    return {
      label: getPluralizedMetadataLabel(metadataKey),
      values: entity[entityKey] as unknown as string[],
    };
  };
};

/**
 * Returns NTagCell component.
 * @param propGetter - Fn that returns props for NTagCell component.
 * @returns NTagCell component.
 */
export function renderNTagCell<T extends RowData>(
  propGetter: (data: T) => ComponentProps<typeof C.NTagCell>
): (ctx: CellContext<T, unknown>) => JSX.Element {
  return ({ row }) => {
    return C.NTagCell(propGetter(row.original));
  };
}
