import { ComponentProps, JSX } from "react";
import { StyledSectionTitle, StyledRoundedPaper } from "./access.styles";
import { Divider, Stack } from "@mui/material";
import { Links } from "@databiosphere/findable-ui/lib/components/Links/links";
import { SectionContent } from "../../../../../../../EntityView/ui/SectionContent/sectionContent";

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
