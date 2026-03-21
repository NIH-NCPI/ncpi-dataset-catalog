import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import {
  bpDownMd,
  bpDownSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Stack } from "@mui/material";
import { Headline } from "../Section/section.styles";

export const StyledSection = styled.section`
  background-color: ${PALETTE.SMOKE_LIGHT};
`;

export const StyledHeadline = styled(Headline)`
  grid-column: 2 / -2;
  margin: 0 auto;
  max-width: 560px;
  text-align: center;
`;

export const StyledStack = styled(Stack)`
  flex-direction: row;
  gap: 16px;
  grid-column: 2 / -2;

  ${bpDownMd} {
    grid-column: 1 / -1;
  }

  ${bpDownSm} {
    flex-direction: column;
  }
`;

export const StyledRoundedPaper = styled(RoundedPaper)`
  align-content: flex-start;
  display: grid;
  flex: 1;
  gap: 16px;
  padding: 16px;

  img {
    height: 40px;
    width: auto;
  }
`;
