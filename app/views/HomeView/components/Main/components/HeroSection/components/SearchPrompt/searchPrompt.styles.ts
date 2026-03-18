import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";
import { Chips } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Messages/components/PromptMessage/components/Chips/chips";
import { Chip, Stack } from "@mui/material";

export const StyledForm = styled("form")`
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 560px;
  width: 100%;

  .MuiBox-root {
    padding: 0;

    .MuiInputBase-root {
      textarea::placeholder {
        color: ${PALETTE.INK_LIGHT};
        opacity: 1;
      }
    }
  }
`;

export const StyledStack = styled(Stack)`
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: center;
`;

export const StyledChips = styled(Chips)`
  display: contents;

  .MuiChip-root {
    background-color: transparent;
  }
`;

export const StyledChip = styled(Chip)`
  background-color: ${PALETTE.PRIMARY_LIGHTEST};
  cursor: pointer;
  height: unset;
  padding: 8px 12px;

  &:hover {
    text-decoration: none;
  }

  &:active {
    box-shadow: none;
  }

  .MuiChip-label {
    color: ${PALETTE.PRIMARY_MAIN};
    padding: 0;
  }
` as typeof Chip;
