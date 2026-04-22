import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";

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
