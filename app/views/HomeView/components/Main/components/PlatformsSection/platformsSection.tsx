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
  StyledFlexBox,
  StyledHeadline,
  StyledRoundedPaper,
  StyledSection,
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
            We connect you to datasets across four NIH cloud platforms.
          </SectionSubtitle>
        </StyledHeadline>
        <StyledFlexBox>
          {PLATFORMS.map(({ description, logo, name }) => (
            <StyledRoundedPaper key={name}>
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
        </StyledFlexBox>
      </StyledContainer>
    </StyledSection>
  );
};
