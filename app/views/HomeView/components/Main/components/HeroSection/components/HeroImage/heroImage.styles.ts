import styled from "@emotion/styled";

export const StyledGridItemA = styled.div`
  grid-column: 1 / 5;
  grid-row: 1;
  position: relative;
  width: 100%;

  img {
    height: auto;
    left: -218px;
    position: absolute;
    top: 242px;
    width: 576px;
  }
`;

export const StyledGridItemB = styled.div`
  grid-column: 8 / -1;
  grid-row: 1;
  position: relative;
  width: 100%;

  img {
    height: auto;
    position: absolute;
    right: -206px;
    top: 198px;
    width: 686px;
  }
`;
