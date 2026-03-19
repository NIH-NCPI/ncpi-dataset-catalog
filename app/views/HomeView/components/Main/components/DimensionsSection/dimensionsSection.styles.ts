import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import {
  bpDownSm,
  bpUpSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Accordion, Box, Container, Stack } from "@mui/material";

const CONTAINER_WIDTH = 924;
const SPACING = 72;

export const StyledSection = styled.section`
  overflow: hidden;
  position: relative; /* positions image container */
`;

export const StyledContainer = styled(Container)`
  && {
    box-sizing: content-box;
    max-width: 1158px;
    padding: ${SPACING}px 16px;
    width: unset;
  }
`;

export const StyledStack = styled(Stack)`
  gap: 32px 16px;
  flex-direction: row;

  ${bpDownSm} {
    flex-direction: column;
  }
`;

export const StyledBox = styled(Box)`
  max-width: 454px;

  ${bpDownSm} {
    max-width: none;
  }
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
  &::after {
    background: linear-gradient(
      180deg,
      rgba(254, 254, 254, 0) 0%,
      #fefefe 100%
    );
    bottom: 0;
    content: "";
    display: block;
    height: ${SPACING}px;
    position: absolute;
    width: 100%;
  }

  ${bpDownSm} {
    margin-bottom: -${SPACING}px;
  }

  ${bpUpSm} {
    height: calc(100% - ${SPACING}px);
    max-width: ${CONTAINER_WIDTH}px;
    position: absolute;
    width: 100%;
  }
`;

export const StyledImage = styled.img`
  height: auto;
  max-width: ${CONTAINER_WIDTH}px;
  width: 100%;

  ${bpDownSm} {
    clip-path: inset(0 0 100px 0);
    height: 100%;
    margin-bottom: -100px;
    width: auto;
  }
`;
