import { HEADER_HEIGHT_VAR } from "@databiosphere/findable-ui/lib/components/Layout/components/Header/common/constants";
import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import { bpDownSm } from "@databiosphere/findable-ui/lib/styles/common/mixins/breakpoints";
import styled from "@emotion/styled";
import { Container, Stack, Typography } from "@mui/material";

export const StyledContainer = styled(Container)`
  && {
    display: grid;
    gap: 24px 16px;
    grid-template-columns: repeat(12, 1fr);
    margin: 0 auto;
    padding: 72px 24px;
  }
`;

// Pulls the sky up under the sticky, transparent header so its gradient shows through.
export const StyledSkyline = styled.div`
  background: linear-gradient(180deg, #c6e1ef 0%, #fefefe 54%);
  margin-top: calc(-1 * ${HEADER_HEIGHT_VAR});
  padding-top: ${HEADER_HEIGHT_VAR};

  ${bpDownSm} {
    background: linear-gradient(180deg, #c6e1ef 0%, #fefefe 36%);
  }
`;

export const Headline = styled(Stack)`
  gap: 8px;
`;

export const SectionTitle = styled(Typography)`
  font-family: "Inter Tight", sans-serif;
  font-size: 32px;
  font-weight: 500;
  line-height: 40px;
` as typeof Typography;

export const SectionSubtitle = styled(Typography)`
  color: ${PALETTE.INK_LIGHT};
  font: ${FONT.BODY_LARGE_400};
` as typeof Typography;
