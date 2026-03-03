import {
  RowData,
  Table,
  TableOptions,
  useReactTable,
} from "@tanstack/react-table";
import { CORE_OPTIONS } from "../../../../../../../../../../components/common/Table/options/core";

/**
 * React hook to create and configure a table instance using TanStack Table.
 * @param options - Table options.
 * @returns Table.
 */
export const useTable = <T extends RowData>(
  options: TableOptions<T>
): { table: Table<T> } => {
  const table = useReactTable<T>({
    ...CORE_OPTIONS,
    enableHiding: true,
    enableTableDownload: true,
    ...options,
  });

  return { table };
};
