import styled from "@emotion/styled";
import { Stack } from "@mui/material";

export const StyledStack = styled(Stack)`
  align-items: center;
  flex: 1;
  justify-content: center;

  .MuiStack-root {
    align-items: center;
    max-width: 408px;
    text-align: center;
  }

  h1 {
    letter-spacing: 0;
  }

  .MuiChip-root {
    background-color: transparent;
  }
`;
