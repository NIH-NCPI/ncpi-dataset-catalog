import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { ROUTES } from "../../../../../../../../../../routes/constants";
import * as C from "../../../../../../../../../components";
import { Study } from "../../../types/study";

/**
 * Builds props for the study entity title Link component.
 * @param ctx - Cell context.
 * @returns Link component.
 */
export const renderTitle = (ctx: CellContext<Study, unknown>): JSX.Element => {
  return C.Link({
    label: ctx.row.original.title,
    url: `${ROUTES.RESEARCH_STUDIES}/${ctx.row.original.dbGapId}`,
  });
};
