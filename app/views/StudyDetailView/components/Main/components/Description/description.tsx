import { MarkdownRenderer } from "@databiosphere/findable-ui/lib/components/MarkdownRenderer/markdownRenderer";
import { ComponentProps, JSX } from "react";
import { StyledSectionTitle, StyledRoundedPaper } from "./description.styles";
import { Divider } from "@mui/material";
import { SectionContent } from "../../../../../EntityView/ui/SectionContent/sectionContent";

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
