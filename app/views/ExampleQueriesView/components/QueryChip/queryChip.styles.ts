import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";
import { Chip } from "@mui/material";

export const StyledForm = styled("form")`
  display: inline;
`;

export const StyledChip = styled(Chip)`
  background-color: ${PALETTE.COMMON_WHITE};
  border-color: ${PALETTE.SMOKE_MAIN};
  color: ${PALETTE.INK_MAIN};
  cursor: pointer;
  height: unset;
  padding: 8px 12px;

  &.MuiChip-clickable:hover {
    background-color: transparent;
  }

  &:active {
    box-shadow: none;
  }

  .MuiChip-label {
    padding: 0;
  }
` as typeof Chip;
