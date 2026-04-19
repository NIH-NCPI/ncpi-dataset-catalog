import { Links } from "@databiosphere/findable-ui/lib/components/Links/links";
import { Divider, Stack } from "@mui/material";
import { ComponentProps, JSX } from "react";
import { SectionContent } from "../../../../../../../EntityView/ui/SectionContent/sectionContent";
import { StyledRoundedPaper, StyledSectionTitle } from "./access.styles";

/**
 * Renders "applying for access" component.
 * @param props - Component props for the Links component.
 * @returns Access component.
 */
export const Access = (props: ComponentProps<typeof Links>): JSX.Element => {
  return (
    <StyledRoundedPaper>
      <StyledSectionTitle>Applying For Access</StyledSectionTitle>
      <Divider />
      <SectionContent>
        <Stack useFlexGap>
          <Links {...props} />
        </Stack>
      </SectionContent>
    </StyledRoundedPaper>
  );
};
