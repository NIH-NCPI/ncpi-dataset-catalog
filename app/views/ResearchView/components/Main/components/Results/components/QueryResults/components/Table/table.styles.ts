import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import styled from "@emotion/styled";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";

export const StyledRoundedPaper = styled(RoundedPaper)`
  display: grid;
  overflow: hidden;

  .MuiTableContainer-root {
    background-color: ${PALETTE.SMOKE_MAIN};

    .MuiTableCell-root {
      word-break: break-word;
    }
  }
`;
