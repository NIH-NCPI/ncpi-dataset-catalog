import { JSX } from "react";
import { SectionSubtitle, SectionTitle } from "../Section/section.styles";
import { List } from "./components/List/list";
import { Stats } from "./components/Stats/stats";
import {
  StyledContainer,
  StyledHeadline,
  StyledSection,
} from "./metadataSection.styles";

/**
 * Renders the metadata section with feature highlights and stat cards.
 * @returns Metadata section.
 */
export const MetadataSection = (): JSX.Element => {
  return (
    <StyledSection>
      <StyledContainer>
        <StyledHeadline useFlexGap>
          <SectionTitle component="h2">More than metadata</SectionTitle>
          <SectionSubtitle component="h3">
            Every study is enriched with data you won&apos;t find on dbGaP
            alone.
          </SectionSubtitle>
        </StyledHeadline>
        <List />
        <Stats />
      </StyledContainer>
    </StyledSection>
  );
};
