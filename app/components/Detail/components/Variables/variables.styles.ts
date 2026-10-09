import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Stack } from "@mui/material";

export const StyledStack = styled(Stack)`
  grid-column: 1 / -1;

  .MuiPaper-root {
    display: grid;
    gap: 8px;
    padding: 20px;

    ${bpDownSm} {
      padding: 20px 16px;
    }
  }
`;

export const VariableRow = styled.li`
  align-items: flex-start;
  border-top: 1px solid ${PALETTE.SMOKE_MAIN};
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  overflow-wrap: anywhere;
  padding: 12px 0;

  ${bpDownSm} {
    gap: 4px;
    grid-template-columns: 1fr;
  }
`;

export const VariableRows = styled.ul`
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
`;
