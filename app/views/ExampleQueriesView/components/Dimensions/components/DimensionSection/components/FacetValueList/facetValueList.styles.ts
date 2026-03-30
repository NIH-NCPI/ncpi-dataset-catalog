import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";

export const StyledValueList = styled("ul")`
  column-count: 3;

  ${bpDownSm} {
    column-count: 1;
  }
`;
