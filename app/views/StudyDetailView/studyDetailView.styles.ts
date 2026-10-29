import styled from "@emotion/styled";
import { Container } from "@mui/material";

export const StyledGrid = styled("div")`
  align-items: flex-start;
  contain: size; /* fills the main row without growing it, so the view scrolls inside the window */
  display: grid;
  height: 100%;
  min-width: 1028px;
  overflow: auto;
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
