import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";
import { Accordion, Box, Container } from "@mui/material";

const MAX_WIDTH = 924;
const PADDING = 72;

export const StyledSection = styled.section`
  overflow: hidden;
  position: relative; /* positions image container */
`;

export const StyledContainer = styled(Container)`
  && {
    box-sizing: content-box;
    max-width: 1158px;
    padding: ${PADDING}px 16px;
    width: unset;
  }
`;

export const StyledBox = styled(Box)`
  max-width: 454px;
`;

export const StyledAccordion = styled(Accordion)`
  padding: 12px 0;

  &:first-of-type {
    box-shadow: inset 0 -1px 0 0 ${PALETTE.SMOKE_MAIN};
  }

  &.Mui-expanded {
    &::after {
      background-color: ${PALETTE.INK_MAIN};
      bottom: 0;
      content: "";
      display: block;
      height: 1px;
      left: 0;
      opacity: 1;
      position: absolute;
      width: 72px;
    }
  }

  .MuiAccordionSummary-root {
    min-height: unset;

    .MuiAccordionSummary-content {
      color: ${PALETTE.INK_LIGHT};
      font: ${FONT.BODY_LARGE_500};
      margin: 4px 0;

      &.Mui-expanded {
        color: ${PALETTE.INK_MAIN};
      }
    }
  }

  .MuiAccordionDetails-root {
    color: ${PALETTE.INK_LIGHT};
    font: ${FONT.BODY_SMALL_400};
    margin-bottom: 4px;
    padding: 0;
  }
`;

export const StyledImageBox = styled(Box)`
  height: calc(100% - ${PADDING}px);
  max-width: ${MAX_WIDTH}px;
  position: absolute;
  width: 100%;

  &::after {
    background: linear-gradient(
      180deg,
      rgba(254, 254, 254, 0) 0%,
      #fefefe 100%
    );
    bottom: 0;
    content: "";
    display: block;
    height: ${PADDING}px;
    position: absolute;
    width: 100%;
  }
`;

export const StyledImage = styled.img`
  height: auto;
  width: 100%;
`;
