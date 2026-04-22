import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { ROUTES } from "../../../../../../../../../../routes/constants";
import * as C from "../../../../../../../../../components";
import { Variable } from "../../../types/variable";

/**
 * Builds props for the dbGapUrl Link component.
 * @param ctx - Cell context.
 * @returns Link component.
 */
export const renderDbGapUrl = (
  ctx: CellContext<Variable, unknown>
): JSX.Element => {
  return C.Link({
    label: ctx.row.original.phvId,
    url: ctx.row.original.dbGapUrl,
  });
};

/**
 * Builds props for the study title Link component.
 * @param ctx - Cell context.
 * @returns Link component.
 */
export const renderStudyTitle = (
  ctx: CellContext<Variable, unknown>
): JSX.Element => {
  return C.Link({
    label: ctx.row.original.studyTitle ?? ctx.row.original.studyId,
    url: `${ROUTES.RESEARCH_STUDIES}/${ctx.row.original.studyId}`,
  });
};
