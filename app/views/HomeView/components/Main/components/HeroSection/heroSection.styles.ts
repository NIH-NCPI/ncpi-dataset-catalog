import styled from "@emotion/styled";
import { Stack } from "@mui/material";

export const StyledStack = styled(Stack)`
  align-items: center;
  margin: 0 auto;
  max-width: 752px;
  padding: 72px 0;

  h1 {
    background: linear-gradient(180deg, #7f8daa 0%, #373c4f 100%);
    background-clip: text;
    font-family: "Inter Tight", sans-serif;
    font-size: 48px;
    font-weight: 500;
    line-height: 56px;
    margin: 0;
    text-align: center;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  h2 {
    text-align: center;
  }
`;
