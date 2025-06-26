import { TableOptions } from "@tanstack/react-table";
import { Attribute } from "./types";
import { COLUMN_DEFS } from "./columnDefs";

export const TABLE_OPTIONS: Omit<
  TableOptions<Attribute>,
  "data" | "getCoreRowModel"
> = {
  columns: COLUMN_DEFS,
  initialState: {
    columnVisibility: {
      classKey: true,
      name: true,
      title: false,
    },
    expanded: true,
    grouping: ["title"],
  },
};
