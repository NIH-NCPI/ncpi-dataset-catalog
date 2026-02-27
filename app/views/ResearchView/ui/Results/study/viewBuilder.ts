import { Study } from "../../Datasets/types/study";
import * as C from "../../../../../components";
import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";

/**
 * Builds props for the study entity title Link component.
 * @param ctx - Cell context.
 * @returns Link component.
 */
export const renderTitle = (ctx: CellContext<Study, unknown>): JSX.Element => {
  return C.Link({
    label: ctx.row.original.title,
    url: `/studies/${ctx.row.original.dbGapId}`,
  });
};
