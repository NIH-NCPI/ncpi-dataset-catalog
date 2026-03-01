import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import styled from "@emotion/styled";
import { SectionTitle } from "../../../../../EntityView/ui/SectionTitle/sectionTitle";
import { SECTION_PADDING } from "../../../../../EntityView/ui/styles";
import { RoundedPaper } from "../../../../../EntityView/ui/RoundedPaper/roundedPaper";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";

export const StyledRoundedPaper = styled(RoundedPaper)`
  align-self: stretch;
  background-color: ${PALETTE.COMMON_WHITE};
  font: ${FONT.BODY_400_2_LINES};
  gap: 0;
`;

export const StyledSectionTitle = styled(SectionTitle)`
  ${SECTION_PADDING};
`;
