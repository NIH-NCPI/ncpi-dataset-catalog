import styled from "@emotion/styled";
import { RequestAccess } from "../../../../components/RequestAccess/requestAccess";

export const StyledGrid = styled.div`
  align-items: flex-start;
  display: grid;
  gap: 64px;
  grid-column: 1 / -1;
  grid-template-columns: 1fr 1fr;
`;

export const StyledRequestAccess = styled(RequestAccess)`
  align-self: flex-start;
`;
