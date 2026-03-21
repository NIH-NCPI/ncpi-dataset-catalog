import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import {
  bpDownMd,
  bpDownSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import {
  StyledContainer as BaseStyledContainer,
  Headline,
} from "../Section/section.styles";

export const StyledSection = styled.section`
  background-color: ${PALETTE.SMOKE_LIGHT};
`;

export const StyledContainer = styled(BaseStyledContainer)`
  grid-template-rows: auto 1fr;

  ${bpDownSm} {
    grid-template-rows: unset;
  }
`;

export const StyledHeadline = styled(Headline)`
  grid-column: 2 / span 4;

  ${bpDownMd} {
    grid-column: 1 / span 5;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
  }
`;
