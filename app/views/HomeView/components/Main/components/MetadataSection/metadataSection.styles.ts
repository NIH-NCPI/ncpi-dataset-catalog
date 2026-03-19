import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Container, Stack } from "@mui/material";

export const StyledSection = styled.section`
  background-color: ${PALETTE.SMOKE_LIGHT};
`;

export const StyledContainer = styled(Container)`
  && {
    box-sizing: content-box;
    max-width: 1158px;
    padding: 72px 16px;
    width: unset;
  }
`;

export const StyledStack = styled(Stack)`
  gap: 32px 16px;
  flex-direction: row;

  > .MuiStack-root:first-of-type {
    > * {
      max-width: 454px;
    }
  }

  ${bpDownSm} {
    flex-direction: column;
  }
`;
