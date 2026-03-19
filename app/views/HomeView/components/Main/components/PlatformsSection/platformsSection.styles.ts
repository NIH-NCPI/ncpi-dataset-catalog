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
  background-color: ${PALETTE.COMMON_WHITE};
`;

export const StyledHeadline = styled(Headline)`
  grid-column: 2 / -2;
  margin: 0 auto;
  max-width: 560px;
  text-align: center;
`;

export const StyledStack = styled(Stack)`
  align-items: center;
  grid-column: 2 / -2;
  text-align: center;
`;

export const StyledFlexBox = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  grid-column: 2 / -2;
  justify-content: flex-start;
  margin-top: 32px;

  ${bpDownMd} {
    grid-column: 1 / -1;
  }
`;

export const StyledRoundedPaper = styled(RoundedPaper)`
  align-items: flex-start;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  justify-content: flex-start;
  min-width: 30%;
  padding: 16px;

  ${bpDownSm} {
    min-width: 100%;
  }

  img {
    height: 40px;
    width: auto;
  }
`;
