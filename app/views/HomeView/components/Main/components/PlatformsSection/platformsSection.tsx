import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Stack, Typography } from "@mui/material";
import { JSX } from "react";
import {
  SectionSubtitle,
  SectionTitle,
  StyledContainer,
} from "../Section/section.styles";
import { PLATFORMS } from "./constants";
import {
  StyledHeadline,
  StyledRoundedPaper,
  StyledSection,
  StyledStack,
} from "./platformsSection.styles";

/**
 * Renders the platforms section.
 * @returns Platforms section.
 */
export const PlatformsSection = (): JSX.Element => {
  return (
    <StyledSection>
      <StyledContainer>
        <StyledHeadline useFlexGap>
          <SectionTitle component="h2">Where the data lives</SectionTitle>
          <SectionSubtitle component="h3">
            We connect you to datasets across five NIH cloud platforms.
          </SectionSubtitle>
        </StyledHeadline>
        <StyledStack useFlexGap>
          {PLATFORMS.map(({ description, logo, name }) => (
            <StyledRoundedPaper key={name}>
              {/* eslint-disable-next-line @next/next/no-img-element -- static export (output: "export") disables next/image optimization; these are small static logos */}
              <img alt={name} src={logo} />
              <Stack spacing={1} useFlexGap>
                <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_500}>
                  {name}
                </Typography>
                <Typography
                  color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
                  variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400_2_LINES}
                >
                  {description}
                </Typography>
              </Stack>
            </StyledRoundedPaper>
          ))}
        </StyledStack>
      </StyledContainer>
    </StyledSection>
  );
};
