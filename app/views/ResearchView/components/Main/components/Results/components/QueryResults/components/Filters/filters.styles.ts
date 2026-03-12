import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";
import { Chip } from "@mui/material";

export const StyledChip = styled(Chip)`
  border-radius: 4px;
  box-shadow: 0 0 0 2px ${PALETTE.COMMON_WHITE};
  cursor: pointer;
  gap: 4px;
  justify-self: flex-start;
  padding: 0 8px;

  .MuiChip-label {
    padding: 0;
  }

  .MuiChip-deleteIcon {
    font-size: 16px;
    margin: 0 -4px 0 0;

    &:hover {
      color: inherit;
    }
  }
`;
