import { textBody400 } from "@databiosphere/findable-ui/lib/styles/common/mixins/fonts";
import { PALETTE } from "@databiosphere/findable-ui/src/styles/common/constants/palette";
import styled from "@emotion/styled";

export const Figure = styled.figure`
  margin: 32px 0;

  img {
    border: 1px solid ${PALETTE.SMOKE_MAIN};
    border-radius: 6px;
    margin: 0 auto;
    max-width: 100%;
  }

  figcaption {
    ${textBody400};
    margin-top: 8px;
    text-align: center;
  }
`;
