import { IdentityCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/identityCell";
import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { ROUTES } from "../../../../../../../../../../routes/constants";
import { buildStudyIdentityChips } from "../../../../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/studyIdentity/utils";
import { Study } from "../../../types/study";
import { getConsentLongNames } from "./utils";

/**
 * Renders the study IdentityCell: the title linked to the research study page,
 * with dbGaP Id, platform and consent code chips.
 * @param ctx - Cell context.
 * @returns IdentityCell component.
 */
export const renderStudyIdentity = (
  ctx: CellContext<Study, unknown>
): JSX.Element => {
  const { consentCodes, dbGapId, platforms, title } = ctx.row.original;
  return IdentityCell({
    chips: buildStudyIdentityChips({
      consentCodes,
      consentLongNames: getConsentLongNames(ctx.table),
      dbGapId,
      platforms,
    }),
    title: {
      label: title,
      url: `${ROUTES.RESEARCH_STUDIES}/${dbGapId}`,
    },
  });
};
