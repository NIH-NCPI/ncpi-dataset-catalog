import { TableOptions } from "@tanstack/react-table";
import { Attribute } from "./types";
import { COLUMN_DEFS } from "./columnDefs";
import slugify from "slugify";

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
