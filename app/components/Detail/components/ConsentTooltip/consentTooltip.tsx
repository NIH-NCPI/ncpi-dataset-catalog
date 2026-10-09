import { Tooltip } from "@mui/material";
import { JSX } from "react";
import type { ConsentTooltipProps } from "./types";
import { getDisplayConsentLongName } from "./utils";

export const ConsentTooltip = ({
  consentCode,
  consentLongName,
}: ConsentTooltipProps): JSX.Element => {
  return (
    <Tooltip
      arrow={true}
      placement="top"
      title={getDisplayConsentLongName(consentLongName) ?? ""}
    >
      <span>{consentCode}</span>
    </Tooltip>
  );
};
