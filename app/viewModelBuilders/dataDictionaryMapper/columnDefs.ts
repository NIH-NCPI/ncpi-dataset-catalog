import { ColumnDef } from "@tanstack/react-table";
import { Attribute } from "./types";
import { FieldCell } from "../../components/DataDictionary/components/TableCell/components/FieldCell/fieldCell";
import { DetailCell } from "../../components/DataDictionary/components/TableCell/components/DetailCell/detailCell";

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
    accessorKey: "details",
    cell: DetailCell,
    enableColumnFilter: false,
    enableGlobalFilter: false,
    header: "Details",
    id: "details",
    meta: { width: "1fr" },
  },
  {
    accessorFn: (row) => (row.required ? "Required" : "Not Required"),
    enableColumnFilter: true,
    enableGlobalFilter: false,
    enableHiding: false,
    filterFn: "arrIncludesSome",
    header: "Required",
    id: "required",
  },
  {
    accessorFn: (row) => row.annotations?.tier,
    enableColumnFilter: false,
    enableGlobalFilter: false,
    enableHiding: false,
    filterFn: "arrIncludesSome",
    header: "Tier",
    id: "tier",
  },
  {
    accessorKey: "name",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Name",
    id: "name",
  },
  {
    accessorKey: "description",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Description",
    id: "description",
  },
  {
    accessorKey: "title",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Title",
    id: "title",
  },
  {
    accessorKey: "rationale",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Rationale",
    id: "rationale",
  },
  {
    accessorKey: "values",
    enableColumnFilter: false,
    enableGlobalFilter: true,
    header: "Allowed Values",
    id: "values",
  },
];
