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
 * Rows follow the sorting in `options.initialState`; header clicks don't sort.
 * @param options - Table options.
 * @returns Table.
 */
export const useTable = <T extends RowData>(
  options: TableOptions<T>
): { table: Table<T> } => {
  const table = useReactTable<T>({
    ...CORE_OPTIONS,
    enableHiding: true,
    enableSortingInteraction: false,
    enableTableDownload: true,
    getSortedRowModel: getSortedRowModel(),
    ...options,
  });

  return { table };
};
