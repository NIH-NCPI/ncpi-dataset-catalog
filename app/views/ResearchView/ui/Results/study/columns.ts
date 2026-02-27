import { ColumnDef } from "@tanstack/react-table";
import { Study } from "../../Datasets/types/study";
import {
  renderNTagCell,
  buildNTagProps,
} from "../../../../../components/common/Table/components/NTagCell/utils";
import { METADATA_KEY } from "app/components/Index/common/entities";
import { renderTitle } from "./viewBuilder";

const CONSENT_CODES: ColumnDef<Study> = {
  accessorKey: "consentCodes",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.CONSENT_CODE, "consentCodes")
  ),
  header: "Consent Code",
  id: "consentCodes",
  meta: { width: { max: "1fr", min: "140px" } },
};

const DATA_TYPES: ColumnDef<Study> = {
  accessorKey: "dataTypes",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.DATA_TYPE, "dataTypes")
  ),
  header: "Data Type",
  id: "dataTypes",
  meta: { width: { max: "1fr", min: "140px" } },
};

const DB_GAP_ID: ColumnDef<Study> = {
  accessorKey: "dbGapId",
  header: "dbGap Id",
  id: "dbGapId",
  meta: { width: { max: "1fr", min: "120px" } },
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
  accessorKey: "platforms",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.PLATFORM, "platforms")
  ),
  header: "Platform",
  id: "platforms",
  meta: { width: { max: "1fr", min: "120px" } },
};

const STUDY_DESIGNS: ColumnDef<Study> = {
  accessorKey: "studyDesigns",
  cell: renderNTagCell<Study>(
    buildNTagProps(METADATA_KEY.STUDY_DESIGN, "studyDesigns")
  ),
  header: "Study Design",
  id: "studyDesigns",
  meta: { width: { max: "1fr", min: "140px" } },
};

const TITLE: ColumnDef<Study> = {
  accessorKey: "title",
  cell: renderTitle,
  header: "Study",
  id: "title",
  meta: { width: { max: "2fr", min: "160px" } },
};

export const COLUMNS: ColumnDef<Study>[] = [
  TITLE,
  DB_GAP_ID,
  PLATFORMS,
  FOCUS,
  DATA_TYPES,
  PARTICIPANT_COUNT,
  STUDY_DESIGNS,
  CONSENT_CODES,
];
