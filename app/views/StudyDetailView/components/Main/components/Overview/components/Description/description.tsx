import { MarkdownRenderer } from "@databiosphere/findable-ui/lib/components/MarkdownRenderer/markdownRenderer";
import { Divider } from "@mui/material";
import { ComponentProps, JSX } from "react";
import { SectionContent } from "../../../../../../../EntityView/ui/SectionContent/sectionContent";
import { StyledRoundedPaper, StyledSectionTitle } from "./description.styles";

/**
 * Renders a description component.
 * @param props - Component props for the MarkdownRenderer.
 * @returns Description component.
 */
export const Description = (
  props: ComponentProps<typeof MarkdownRenderer>
): JSX.Element => {
  return (
    <StyledRoundedPaper>
      <StyledSectionTitle>Description</StyledSectionTitle>
      <Divider />
      <SectionContent>
        <MarkdownRenderer {...props} />
      </SectionContent>
    </StyledRoundedPaper>
  );
};
