import {
  ANCHOR_TARGET,
  REL_ATTRIBUTE,
} from "@databiosphere/findable-ui/lib/components/Links/common/entities";
import { LINK_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/link";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Link, Stack, Typography } from "@mui/material";
import { JSX } from "react";
import {
  SectionSubtitle,
  SectionTitle,
  StyledContainer,
} from "../Section/section.styles";
import { ACCESS_OPTIONS } from "./constants";
import {
  StyledHeadline,
  StyledRoundedPaper,
  StyledSection,
  StyledStack,
} from "./dataAccessSection.styles";

/**
 * Renders the data access section with dbGaP and DUOS access cards.
 * @returns Data access section.
 */
export const DataAccessSection = (): JSX.Element => {
  return (
    <StyledSection>
      <StyledContainer>
        <StyledHeadline useFlexGap>
          <SectionTitle component="h2">Ready to access the data?</SectionTitle>
          <SectionSubtitle component="h3">
            This catalog uses only publicly available metadata. To work with
            individual-level data, apply through dbGaP or DUOS.
          </SectionSubtitle>
        </StyledHeadline>
        <StyledStack spacing={2} useFlexGap>
          {ACCESS_OPTIONS.map((option) => (
            <StyledRoundedPaper key={option.name}>
              <img alt={option.name} src={option.logo} />
              <Stack spacing={1} useFlexGap>
                <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_500}>
                  {option.name}
                </Typography>
                <Typography
                  color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
                  variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400_2_LINES}
                >
                  {option.description}
                </Typography>
              </Stack>
              <Link
                rel={REL_ATTRIBUTE.NO_OPENER_NO_REFERRER}
                target={ANCHOR_TARGET.BLANK}
                underline={LINK_PROPS.UNDERLINE.NONE}
                variant={TYPOGRAPHY_PROPS.VARIANT.BODY_500}
                {...option.link}
              />
            </StyledRoundedPaper>
          ))}
        </StyledStack>
      </StyledContainer>
    </StyledSection>
  );
};
