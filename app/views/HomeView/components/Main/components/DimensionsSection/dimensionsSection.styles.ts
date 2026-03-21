import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import {
  bpDownMd,
  bpDownSm,
  bpUpSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Accordion, Box } from "@mui/material";
import { Headline, SectionTitle } from "../Section/section.styles";

const CONTAINER_WIDTH = 924;
const SPACING = 72;

export const StyledSection = styled.section`
  overflow: hidden;
  position: relative; /* positions image container */
`;

export const StyledHeadline = styled(Headline)`
  grid-column: 2 / span 5;

  ${bpDownMd} {
    grid-column: 1 / span 5;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
  }
`;

export const StyledSectionTitle = styled(SectionTitle)`
  display: flex;
  flex-direction: column;
` as typeof SectionTitle;

export const StyledLeftBox = styled(Box)`
  grid-column: 2 / span 4;

  ${bpDownMd} {
    grid-column: 1 / span 5;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
  }
`;

export const StyledRightBox = styled(Box)`
  grid-column: 7 / -2;
  grid-row: 1 / 3;

  ${bpDownMd} {
    grid-column: 7 / -1;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
    grid-row: unset;
    margin-bottom: -${SPACING}px;
  }
`;

export const StyledAccordion = styled(Accordion)`
  padding: 12px 0;

  &:first-of-type {
    box-shadow: inset 0 -1px 0 0 ${PALETTE.SMOKE_MAIN};
  }

  @keyframes expand-line {
    from {
      width: 0;
    }
    to {
      width: 100%;
    }
  }

  &::after {
    background-color: ${PALETTE.PRIMARY_MAIN};
    bottom: 0;
    content: "";
    height: 1px;
    left: 0;
    position: absolute;
    width: 0;
  }

  &.Mui-expanded::after {
    animation: expand-line 5000ms linear forwards;
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

  &:hover {
    .MuiAccordionSummary-content {
      color: ${PALETTE.INK_MAIN};
    }
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
