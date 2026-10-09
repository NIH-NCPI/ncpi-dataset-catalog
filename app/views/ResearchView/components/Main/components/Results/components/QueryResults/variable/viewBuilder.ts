import { Link } from "@databiosphere/findable-ui/lib/components/Links/components/Link/link";
import { IdentityCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/identityCell";
import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { ROUTES } from "../../../../../../../../../../routes/constants";
import { buildVariableIdentityChips } from "../../../../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/variableIdentity/utils";
import { Variable } from "../../../types/variable";

/**
 * Builds props for the dbGapUrl Link component.
 * @param ctx - Cell context.
 * @returns Link component.
 */
export const renderDbGapUrl = (
  ctx: CellContext<Variable, unknown>
): JSX.Element => {
  return Link({
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
  return Link({
    label: ctx.row.original.studyTitle ?? ctx.row.original.studyId,
    url: `${ROUTES.RESEARCH_STUDIES}/${ctx.row.original.studyId}`,
  });
};

/**
 * Renders the variable IdentityCell: the concept as plain text, with a variable name chip.
 * @param ctx - Cell context.
 * @returns IdentityCell component.
 */
export const renderVariableIdentity = (
  ctx: CellContext<Variable, unknown>
): JSX.Element => {
  const { concept, variableName } = ctx.row.original;
  return IdentityCell({
    chips: buildVariableIdentityChips(variableName),
    title: { label: concept, url: "" },
  });
};
