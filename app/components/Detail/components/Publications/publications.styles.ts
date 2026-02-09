import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Stack } from "@mui/material";

export const StyledStack = styled(Stack)`
  grid-column: 1 / -1;

  .MuiPaper-root {
    display: grid;
    gap: 8px;
    padding: 20px;

    ${bpDownSm} {
      padding: 20px 16px;
    }
  }
`;
