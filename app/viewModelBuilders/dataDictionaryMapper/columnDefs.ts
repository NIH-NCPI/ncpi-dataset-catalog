import { ColumnDef } from "@tanstack/react-table";
import { Attribute } from "./types";
import { FieldCell } from "app/components/DataDictionary/components/TableCell/components/FieldCell/fieldCell";

export const COLUMN_DEFS: ColumnDef<Attribute>[] = [
  {
    accessorKey: "classKey",
    enableColumnFilter: false,
    enableGlobalFilter: false,
    enableGrouping: true,
    header: "Class Key",
    id: "classKey",
  },
  {
    accessorKey: "field",
    cell: FieldCell,
    enableColumnFilter: false,
    enableGlobalFilter: false,
    header: "Field",
    id: "field",
    meta: { width: { max: "264px", min: "264px" } },
  },
  {
    accessorKey: "name",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Name",
    id: "name",
  },
  {
    accessorKey: "title",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Title",
    id: "title",
  },
];
