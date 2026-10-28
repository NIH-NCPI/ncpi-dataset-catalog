import styled from "@emotion/styled";
import { Grid } from "@mui/material";

export const StyledGrid = styled(Grid)`
  align-content: flex-start;
  contain: size; /* fills the main row without growing it, so long results scroll inside the window */
  display: grid;
  flex: 1;
  gap: 0;
  grid-template-rows: auto 1fr;
  height: 100%;
  min-width: 868px;
  overflow: hidden;

  form {
    align-content: flex-start;
    box-sizing: border-box;
    height: unset;
    margin: 24px;
    min-width: 0;
    overflow: hidden;
  }
`;
