import { LayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/types";
import styled from "@emotion/styled";
import { Container } from "@mui/material";

export const StyledGrid = styled("div", {
  shouldForwardProp: (prop) => prop !== "bottom" && prop !== "top",
})<LayoutSpacing>`
  align-items: flex-start;
  display: grid;
  height: 100%;
  max-height: 100vh;
  min-width: 1028px;
  overflow: auto;
  padding-top: ${({ top }) => top}px;
  width: 100%;
`;

export const StyledContainer = styled(Container)`
  && {
    display: grid;
    gap: 16px;
    grid-column: 1 / -1;
    grid-template-columns: minmax(660px, 1fr) minmax(304px, 0.46fr);
    padding: 24px;
  }
`;
