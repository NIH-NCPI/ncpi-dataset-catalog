import { ColumnDef } from "@tanstack/react-table";
import { Attribute } from "./types";
import { FieldCell } from "../../components/DataDictionary/components/TableCell/components/FieldCell/fieldCell";
import { DetailCell } from "../../components/DataDictionary/components/TableCell/components/DetailCell/detailCell";
import { COLUMN_IDENTIFIERS } from "./columnIds";
import { GridTrackSize } from "@databiosphere/findable-ui/lib/config/entities";

const CLASS_KEY: ColumnDef<Attribute, unknown> = {
  accessorKey: "classKey",
  enableColumnFilter: false,
  enableGlobalFilter: false,
  enableGrouping: true,
  header: "Class Key",
  id: COLUMN_IDENTIFIERS.CLASS_KEY,
};

const DESCRIPTION: ColumnDef<Attribute, unknown> = {
  accessorKey: "description",
  enableColumnFilter: false,
  enableGlobalFilter: true,
  header: "Description",
  id: COLUMN_IDENTIFIERS.DESCRIPTION,
};

const DETAILS: ColumnDef<Attribute, unknown> = {
  accessorKey: "details",
  cell: DetailCell,
  enableColumnFilter: false,
  enableGlobalFilter: false,
  header: "Description",
  id: COLUMN_IDENTIFIERS.DETAILS,
  meta: { width: { max: "1fr", min: "396px" } },
};

const FIELD: ColumnDef<Attribute, unknown> = {
  accessorKey: "field",
  cell: FieldCell,
  enableColumnFilter: false,
  enableGlobalFilter: false,
  header: "Field",
  id: COLUMN_IDENTIFIERS.FIELD,
  meta: {
    columnPinned: true,
    width:
      "round(up, clamp(min(31.26%, 352px), 31.26%, 496px), 1px)" as GridTrackSize,
  },
};

const NAME: ColumnDef<Attribute, unknown> = {
  accessorKey: "name",
  enableColumnFilter: false,
  enableGlobalFilter: true,
  header: "Name",
  id: COLUMN_IDENTIFIERS.NAME,
};

const RATIONALE: ColumnDef<Attribute, unknown> = {
  accessorKey: "rationale",
  enableColumnFilter: false,
  enableGlobalFilter: true,
  header: "Rationale",
  id: COLUMN_IDENTIFIERS.RATIONALE,
};

const REQUIRED: ColumnDef<Attribute, unknown> = {
  accessorFn: (row) => (row.required ? "Required" : "Not Required"),
  enableColumnFilter: true,
  enableGlobalFilter: false,
  enableHiding: false,
  filterFn: "arrIncludesSome",
  header: "Required",
  id: COLUMN_IDENTIFIERS.REQUIRED,
};

const SOURCE: ColumnDef<Attribute, unknown> = {
  accessorFn: (row) => row.source?.children || "None",
  enableColumnFilter: true,
  enableGlobalFilter: false,
  enableHiding: false,
  filterFn: "arrIncludesSome",
  header: "Source",
  id: COLUMN_IDENTIFIERS.SOURCE,
};

const TITLE: ColumnDef<Attribute, unknown> = {
  accessorKey: "title",
  enableColumnFilter: false,
  enableGlobalFilter: true,
  header: "Title",
  id: COLUMN_IDENTIFIERS.TITLE,
};

const VALUES: ColumnDef<Attribute, unknown> = {
  accessorKey: "values",
  enableColumnFilter: false,
  enableGlobalFilter: true,
  header: "Allowed Values",
  id: COLUMN_IDENTIFIERS.VALUES,
};

export const COLUMN_DEFS: ColumnDef<Attribute>[] = [
  CLASS_KEY,
  FIELD,
  DETAILS,
  /* COLUMN FILTERS */
  REQUIRED,
  SOURCE,
  /* GLOBAL FILTERS */
  NAME,
  DESCRIPTION,
  TITLE,
  RATIONALE,
  VALUES,
];
