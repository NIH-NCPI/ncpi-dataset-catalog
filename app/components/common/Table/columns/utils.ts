import type {
  ColumnDef,
  RowData,
  VisibilityState,
} from "@tanstack/react-table";

/**
 * Builds a column visibility state that hides the given columns.
 * @param columns - Columns to hide.
 * @returns Column visibility state, keyed by column id.
 */
export function buildHiddenColumnVisibility<T extends RowData>(
  columns: ColumnDef<T>[]
): VisibilityState {
  return Object.fromEntries(columns.map(({ id }) => [id, false]));
}
