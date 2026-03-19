import { Stack } from "@mui/material";
import { JSX } from "react";
import {
  Headline,
  SectionSubtitle,
  SectionTitle,
} from "../Section/section.styles";
import { List } from "./components/List/list";
import { Stats } from "./components/Stats/stats";
import {
  StyledContainer,
  StyledSection,
  StyledStack,
} from "./metadataSection.styles";

/**
 * Renders the metadata section with feature highlights and stat cards.
 * @returns Metadata section.
 */
export const MetadataSection = (): JSX.Element => {
  return (
    <StyledSection>
      <StyledContainer>
        <StyledStack useFlexGap>
          <Stack flex={1} spacing={4} useFlexGap>
            <Stack spacing={6} useFlexGap>
              <Headline useFlexGap>
                <SectionTitle component="h2">More than metadata</SectionTitle>
                <SectionSubtitle component="h3">
                  Every study is enriched with data you won&apos;t find on dbGaP
                  alone.
                </SectionSubtitle>
              </Headline>
              <List />
            </Stack>
          </Stack>
          <Stack flex={1} useFlexGap>
            <Stats />
          </Stack>
        </StyledStack>
      </StyledContainer>
    </StyledSection>
  );
};
