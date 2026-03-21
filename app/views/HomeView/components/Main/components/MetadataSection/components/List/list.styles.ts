import {
  bpDownMd,
  bpDownSm,
} from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { List } from "@mui/material";

export const StyledList = styled(List)`
  display: flex;
  flex-direction: column;
  gap: 16px;
  grid-column: 2 / span 4;

  ${bpDownMd} {
    grid-column: 1 / span 5;
  }

  ${bpDownSm} {
    grid-column: 1 / -1;
  }

  .MuiListItem-root {
    gap: 8px;
  }

  .MuiListItemIcon-root {
    margin: 0;
    min-width: unset;
  }

  .MuiSvgIcon-root {
    color: #065f46;
  }
`;
