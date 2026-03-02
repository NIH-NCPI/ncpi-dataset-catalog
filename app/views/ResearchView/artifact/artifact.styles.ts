import { LayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/types";
import styled from "@emotion/styled";
import { Grid } from "@mui/material";

export const StyledGrid = styled(Grid, {
  shouldForwardProp: (prop) => prop !== "bottom" && prop !== "top",
})<LayoutSpacing>`
  align-content: flex-start;
  display: grid;
  flex: 1;
  gap: 0;
  grid-template-rows: auto 1fr;
  height: 100%;
  max-height: 100vh;
  min-width: 868px;
  overflow: hidden;
  padding-top: ${({ top }) => top}px;

  form {
    align-content: flex-start;
    box-sizing: border-box;
    height: unset;
    margin: 24px;
    min-width: 0;
    overflow: hidden;
  }
`;
