import { Stack, Typography } from "@mui/material";
import { JSX } from "react";
import { StyledStack } from "./heroSection.styles";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { SearchPrompt } from "./components/SearchPrompt/searchPrompt";

/**
 * Renders the hero section, headings and AI assisted search prompt.
 * @returns Hero section.
 */
export const HeroSection = (): JSX.Element => {
  return (
    <StyledStack spacing={8} useFlexGap>
      <Stack spacing={4} useFlexGap>
        <h1>Find the right study, faster</h1>
        <Typography
          color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
          component="h2"
          variant={TYPOGRAPHY_PROPS.VARIANT.BODY_LARGE_400_2_LINES}
        >
          Search dbGaP studies with natural language across study metadata,
          semantically harmonized variables, disease hierarchies, and consent
          codes. Then apply for access or view the study on its cloud platform.
        </Typography>
      </Stack>
      <SearchPrompt />
    </StyledStack>
  );
};
