import styled from "@emotion/styled";
import { List } from "@mui/material";

export const StyledList = styled(List)`
  display: flex;
  flex-direction: column;
  gap: 16px;

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
