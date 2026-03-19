import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Stack, Typography } from "@mui/material";
import { JSX } from "react";
import { SectionTitle } from "../Section/section.styles";
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
              <Stack spacing={2} useFlexGap>
                <SectionTitle component="h2">More than metadata</SectionTitle>
                <Typography
                  color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
                  variant={TYPOGRAPHY_PROPS.VARIANT.BODY_LARGE_400_2_LINES}
                >
                  Every study is enriched with data you won&apos;t find on dbGaP
                  alone.
                </Typography>
              </Stack>
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
