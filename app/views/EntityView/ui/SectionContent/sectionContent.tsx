import { StackProps } from "@mui/material";
import { JSX } from "react";
import { StyledBox } from "./sectionContent.styles";

/**
 * Renders a section content component.
 * @param props - Props.
 * @returns SectionContent component.
 */
export const SectionContent = (props: StackProps): JSX.Element => {
  return <StyledBox {...props} />;
};
