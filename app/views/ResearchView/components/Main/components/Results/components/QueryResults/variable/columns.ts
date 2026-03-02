import { ColumnDef } from "@tanstack/react-table";
import { Variable } from "../../../types/variable";
import { renderDbGapUrl, renderStudyTitle } from "./viewBuilder";

const CONCEPT: ColumnDef<Variable> = {
  accessorKey: "concept",
  header: "Concept",
  id: "concept",
  meta: { width: { max: "1fr", min: "140px" } },
};

const DB_GAP_URL: ColumnDef<Variable> = {
  accessorKey: "dbGapUrl",
  cell: renderDbGapUrl,
  header: "dbGap",
  id: "dbGapUrl",
  meta: { width: { max: "1fr", min: "120px" } },
};

const DESCRIPTION: ColumnDef<Variable> = {
  accessorKey: "description",
  header: "Description",
  id: "description",
  meta: { width: { max: "1fr", min: "140px" } },
};

const STUDY_TITLE: ColumnDef<Variable> = {
  accessorKey: "studyTitle",
  cell: renderStudyTitle,
  header: "Study",
  id: "studyTitle",
  meta: { width: { max: "1fr", min: "120px" } },
};

const VARIABLE_NAME: ColumnDef<Variable> = {
  accessorKey: "variableName",
  header: "Variable Name",
  id: "variableName",
  meta: { width: { max: "2fr", min: "160px" } },
};

export const COLUMNS: ColumnDef<Variable>[] = [
  CONCEPT,
  VARIABLE_NAME,
  DESCRIPTION,
  STUDY_TITLE,
  DB_GAP_URL,
];
