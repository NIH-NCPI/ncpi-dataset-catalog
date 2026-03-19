import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import styled from "@emotion/styled";
import { Box, Typography } from "@mui/material";

export const StyledGrid = styled(Box)`
  align-items: center;
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, 1fr);
  height: 100%;

  ${({ theme }) => theme.breakpoints.down(860)} {
    grid-template-columns: 1fr;
  }
`;

export const StyledRoundedPaper = styled(RoundedPaper)`
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  padding: 16px 32px;
`;

export const StyledTypography = styled(Typography)`
  background: linear-gradient(180deg, #6b7996 0%, #373c4f 100%);
  background-clip: text;
  font-family: "Inter Tight", sans-serif;
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
`;
