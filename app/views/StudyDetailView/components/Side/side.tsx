import { JSX } from "react";
import { Props } from "./types";
import { KeyValuePairs } from "@databiosphere/findable-ui/lib/components/common/KeyValuePairs/keyValuePairs";
import {
  buildPlatformLinks,
  buildStudyDetails,
  buildStudySummary,
} from "../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import { Section } from "../../../EntityView/ui/Section/section";
import { KeyValueSection } from "./components/KeyValueSection/keyValueSection";
import { Links } from "@databiosphere/findable-ui/lib/components/Links/links";
import { StyledRoundedPaper } from "./side.styles";

/**
 * Renders the side section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @returns Side section of the study detail view.
 */
export const Side = ({ study }: Props): JSX.Element => {
  return (
    <StyledRoundedPaper>
      <Section>
        <KeyValuePairs {...buildStudyDetails(study)} />
      </Section>
      <Section>
        <Links {...buildPlatformLinks(study)} />
      </Section>
      <KeyValueSection {...buildStudySummary(study)} />
    </StyledRoundedPaper>
  );
};
