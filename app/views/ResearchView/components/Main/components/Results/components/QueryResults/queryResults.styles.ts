import styled from "@emotion/styled";
import { Title } from "@databiosphere/findable-ui/lib/components/common/Title/title";
import { Stack } from "@mui/material";

export const StyledStack = styled(Stack)`
  min-height: 0;
`;

export const StyledTitle = styled(Title)`
  && {
    font-size: 20px;
    letter-spacing: normal;
    line-height: 28px;
  }
`;
