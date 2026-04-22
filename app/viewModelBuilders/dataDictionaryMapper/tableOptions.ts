import { TableOptions } from "@tanstack/react-table";
import slugify from "slugify";
import { COLUMN_DEFS } from "./columnDefs";
import { Attribute } from "./types";

export const TABLE_OPTIONS: Omit<
  TableOptions<Attribute>,
  "data" | "getCoreRowModel"
> = {
  columns: COLUMN_DEFS,
  getRowId: (row) => slugify(`${row.classKey}-${row.name}`),
  initialState: {
    columnVisibility: {
      classKey: true,
      description: false,
      name: false,
      rationale: false,
      required: false,
      title: false,
      values: false,
    },
    grouping: ["classKey"],
  },
};
