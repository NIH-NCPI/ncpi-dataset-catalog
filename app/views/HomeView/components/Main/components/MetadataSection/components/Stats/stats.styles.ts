import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import {
  bpDownMd,
  bpDownSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Stack, Typography } from "@mui/material";

export const StyledStack = styled(Stack)`
  align-items: center;
  display: grid;
  gap: 8px;
  grid-column: 7 / -2;
  grid-row: 1 / span 2;
  grid-template-columns: repeat(2, 1fr);

  ${bpDownMd} {
    grid-column: 7 / -1;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
    grid-row: unset;
  }
`;

export const StyledRoundedPaper = styled(RoundedPaper)`
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  padding: 16px 32px;
`;

export const StyledTypography = styled(Typography)`
  background: linear-gradient(180deg, #6b7996 0%, #373c4f 100%);
  background-clip: text;
  font-family: "Inter Tight", sans-serif;
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
`;
