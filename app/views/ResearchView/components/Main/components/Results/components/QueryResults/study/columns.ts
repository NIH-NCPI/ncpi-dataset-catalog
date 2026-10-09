import type { ColumnDef, InitialTableState } from "@tanstack/react-table";
import { ALWAYS_HIDDEN_COLUMN } from "../../../../../../../../../components/common/Table/columns/constants";
import { buildHiddenColumnVisibility } from "../../../../../../../../../components/common/Table/columns/utils";
import {
  buildNTagProps,
  renderNTagCell,
} from "../../../../../../../../../components/common/Table/components/NTagCell/utils";
import { METADATA_KEY } from "../../../../../../../../../components/Index/common/entities";
import { Study } from "../../../types/study";
import { renderStudyIdentity } from "./viewBuilder";

const CONSENT_CODES: ColumnDef<Study> = {
  ...ALWAYS_HIDDEN_COLUMN,
  accessorKey: "consentCodes",
  header: "Consent Code",
  // Rename id to `consentCodes` to avoid conflict with the consentCode facet "Study Consent"
  id: "consentCodes",
};

const DATA_TYPES: ColumnDef<Study> = {
  accessorKey: "dataTypes",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.DATA_TYPE, "dataTypes")
  ),
  header: "Data Type",
  id: "dataType",
  meta: { width: { max: "1fr", min: "140px" } },
};

const DB_GAP_ID: ColumnDef<Study> = {
  ...ALWAYS_HIDDEN_COLUMN,
  accessorKey: "dbGapId",
  header: "dbGap Id",
  id: "dbGapId",
};

const FOCUS: ColumnDef<Study> = {
  accessorKey: "focus",
  header: "Focus / Disease",
  id: "focus",
  meta: { width: { max: "1fr", min: "140px" } },
};

const PARTICIPANT_COUNT: ColumnDef<Study> = {
  accessorKey: "participantCount",
  header: "Participants",
  id: "participantCount",
  meta: { width: { max: "1fr", min: "120px" } },
};

const PLATFORMS: ColumnDef<Study> = {
  ...ALWAYS_HIDDEN_COLUMN,
  accessorKey: "platforms",
  header: "Platform",
  id: "platform",
};

const STUDY_DESIGNS: ColumnDef<Study> = {
  accessorKey: "studyDesigns",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.STUDY_DESIGN, "studyDesigns")
  ),
  header: "Study Design",
  id: "studyDesign",
  meta: { width: { max: "1fr", min: "140px" } },
};

const STUDY_ID = "title";

const STUDY: ColumnDef<Study> = {
  accessorKey: STUDY_ID,
  cell: renderStudyIdentity,
  enableSorting: true,
  header: "Study",
  id: STUDY_ID,
  meta: { columnPinned: true, width: { max: "1.5fr", min: "340px" } },
  // Explicit: TanStack's "auto" picks a case-sensitive sort for 10 or fewer rows.
  sortingFn: "alphanumeric",
};

// dbGaP Id, Platform and Consent Code render as chips in the Study column.
// Their columns stay, always hidden, so the table download keeps them and the
// filters can still resolve their labels.
const HIDDEN_COLUMNS: ColumnDef<Study>[] = [
  DB_GAP_ID,
  PLATFORMS,
  CONSENT_CODES,
];

export const COLUMNS: ColumnDef<Study>[] = [
  STUDY,
  ...HIDDEN_COLUMNS,
  FOCUS,
  DATA_TYPES,
  STUDY_DESIGNS,
  PARTICIPANT_COUNT,
];

// Rows start sorted by title; only the Study header sorts (see useTable).
export const INITIAL_STATE: InitialTableState = {
  columnVisibility: buildHiddenColumnVisibility(HIDDEN_COLUMNS),
  sorting: [{ desc: false, id: STUDY_ID }],
};
