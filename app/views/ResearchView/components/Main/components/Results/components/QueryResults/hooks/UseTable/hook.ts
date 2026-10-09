import {
  getSortedRowModel,
  type RowData,
  type Table,
  type TableOptions,
  useReactTable,
} from "@tanstack/react-table";
import { CORE_OPTIONS } from "../../../../../../../../../../components/common/Table/options/core";

/**
 * React hook to create and configure a table instance using TanStack Table.
 * Rows start in the sorting from `options.initialState`. Columns are unsortable unless
 * their definition sets `enableSorting: true`; clicking a sortable header toggles
 * ascending/descending.
 * @param options - Table options.
 * @returns Table.
 */
export const useTable = <T extends RowData>(
  options: TableOptions<T>
): { table: Table<T> } => {
  const table = useReactTable<T>({
    ...CORE_OPTIONS,
    defaultColumn: { enableSorting: false },
    enableHiding: true,
    enableSortingInteraction: true,
    enableSortingRemoval: false,
    enableTableDownload: true,
    getSortedRowModel: getSortedRowModel(),
    ...options,
  });

  return { table };
};
