import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";

export const StyledRoundedPaper = styled(RoundedPaper)`
  align-self: flex-start;
  background-color: ${PALETTE.SMOKE_MAIN};
  display: grid;
  gap: 1px;
  min-width: 0;
`;
