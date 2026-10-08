import type { ColumnDef, InitialTableState } from "@tanstack/react-table";
import { ALWAYS_HIDDEN_COLUMN } from "../../../../../../../../../components/common/Table/columns/constants";
import { buildHiddenColumnVisibility } from "../../../../../../../../../components/common/Table/columns/utils";
import { Variable } from "../../../types/variable";
import {
  renderDbGapUrl,
  renderStudyTitle,
  renderVariableIdentity,
} from "./viewBuilder";

const CONCEPT: ColumnDef<Variable> = {
  ...ALWAYS_HIDDEN_COLUMN,
  accessorKey: "concept",
  header: "Concept",
  id: "concept",
};

const DB_GAP_URL: ColumnDef<Variable> = {
  accessorKey: "dbGapUrl",
  cell: renderDbGapUrl,
  header: "dbGap",
  id: "dbGapUrl",
  meta: { width: { max: "1fr", min: "140px" } },
};

const DESCRIPTION: ColumnDef<Variable> = {
  accessorKey: "description",
  header: "Description",
  id: "description",
  meta: { width: { max: "1fr", min: "220px" } },
};

const STUDY_TITLE: ColumnDef<Variable> = {
  accessorKey: "studyTitle",
  cell: renderStudyTitle,
  header: "Study",
  id: "studyTitle",
  meta: { width: { max: "1fr", min: "200px" } },
};

const VARIABLE_ID = "variable";

// Sorts by concept; left out of the download, which keeps the hidden Concept
// and Variable Name columns instead.
const VARIABLE: ColumnDef<Variable> = {
  accessorKey: "concept",
  cell: renderVariableIdentity,
  enableTableDownload: false,
  header: "Variable",
  id: VARIABLE_ID,
  meta: { columnPinned: true, width: { max: "1fr", min: "240px" } },
  // Case-insensitive lexical order, matching the backend's ORDER BY so its
  // 500-row LIMIT keeps the rows shown first. ("auto" would also go
  // case-sensitive for 10 or fewer rows.)
  sortingFn: "text",
};

const VARIABLE_NAME: ColumnDef<Variable> = {
  ...ALWAYS_HIDDEN_COLUMN,
  accessorKey: "variableName",
  header: "Variable Name",
  id: "variableName",
};

// Concept and Variable Name render in the Variable column. Their columns stay,
// always hidden, so the table download keeps them.
const HIDDEN_COLUMNS: ColumnDef<Variable>[] = [CONCEPT, VARIABLE_NAME];

export const COLUMNS: ColumnDef<Variable>[] = [
  VARIABLE,
  ...HIDDEN_COLUMNS,
  DESCRIPTION,
  STUDY_TITLE,
  DB_GAP_URL,
];

// Rows start sorted by concept; headers stay unsortable (see useTable).
export const INITIAL_STATE: InitialTableState = {
  columnVisibility: buildHiddenColumnVisibility(HIDDEN_COLUMNS),
  sorting: [{ desc: false, id: VARIABLE_ID }],
};
