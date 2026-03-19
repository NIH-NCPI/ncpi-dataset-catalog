import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Typography } from "@mui/material";
import { JSX } from "react";
import { STATS } from "./constants";
import {
  StyledGrid,
  StyledRoundedPaper,
  StyledTypography,
} from "./stats.styles";

/**
 * Renders the stat cards grid.
 * @returns Stats grid.
 */
export const Stats = (): JSX.Element => {
  return (
    <StyledGrid>
      {STATS.map(({ label, value }) => (
        <StyledRoundedPaper key={label}>
          <StyledTypography>{value}</StyledTypography>
          <Typography
            color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
            variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400}
          >
            {label}
          </Typography>
        </StyledRoundedPaper>
      ))}
    </StyledGrid>
  );
};
