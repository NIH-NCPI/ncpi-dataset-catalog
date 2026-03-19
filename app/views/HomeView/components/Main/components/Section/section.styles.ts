import styled from "@emotion/styled";
import { Container, Typography } from "@mui/material";

export const StyledContainer = styled(Container)`
  && {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(12, 1fr);
    margin: 0 auto;
    padding: 72px 24px;
  }
`;

export const StyledSectionHeading = styled(Typography)`
  font-family: "Inter Tight", sans-serif;
  font-size: 32px;
  font-weight: 500;
  line-height: 40px;
` as typeof Typography;
