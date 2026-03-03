import { KeyValuePairs } from "@databiosphere/findable-ui/lib/components/common/KeyValuePairs/keyValuePairs";
import { Fragment, JSX } from "react";
import { StyledSection } from "./keyValueSection.styles";
import { Props } from "./type";
import { KeyElType } from "../../../../../EntityView/ui/KeyElType/keyElType";
import { KeyValueElType } from "../../../../../EntityView/ui/KeyValueElType/keyValueElType";
import { SectionTitle } from "../../../../../EntityView/ui/SectionTitle/sectionTitle";

/**
 * Renders a key-value section.
 * @param props - Props.
 * @param props.title - Section title.
 * @returns Key-value section.
 */
export const KeyValueSection = ({ title, ...props }: Props): JSX.Element => {
  return (
    <StyledSection>
      <SectionTitle>{title}</SectionTitle>
      <KeyValuePairs
        KeyElType={KeyElType}
        KeyValueElType={KeyValueElType}
        KeyValuesElType={Fragment}
        {...props}
      />
    </StyledSection>
  );
};
