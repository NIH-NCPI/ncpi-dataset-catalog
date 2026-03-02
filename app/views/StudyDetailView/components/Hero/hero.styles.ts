import styled from "@emotion/styled";
import { RequestAccess } from "../../../../components/RequestAccess/requestAccess";
import { Title } from "@databiosphere/findable-ui/lib/components/common/Title/title";

export const StyledGrid = styled.div`
  align-items: flex-start;
  display: grid;
  gap: 64px;
  grid-column: 1 / -1;
  grid-template-columns: 1fr 1fr;
`;

export const StyledRequestAccess = styled(RequestAccess)`
  align-self: flex-start;
  justify-self: flex-end;
`;

export const StyledTitle = styled(Title)`
  && {
    font-size: 20px;
    letter-spacing: normal;
    line-height: 28px;
    padding: 4px 0;
  }
`;
