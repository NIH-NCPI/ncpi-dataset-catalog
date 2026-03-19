import { STACK_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/stack";
import {
  AccordionDetails,
  AccordionSummary,
  Slide,
  Stack,
} from "@mui/material";
import { JSX } from "react";
import { StyledSectionHeading } from "../Section/section.styles";
import { ACCORDION, IMAGE } from "./accordion";
import { ACCORDION_PROPS, SLIDE_PROPS } from "./constants";
import {
  StyledAccordion,
  StyledBox,
  StyledContainer,
  StyledImage,
  StyledImageBox,
  StyledSection,
} from "./dimensionsSection.styles";
import { useAutoCycle } from "./hooks/UseAutoCycle/hook";

/**
 * Renders the dimensions section with an auto-cycling accordion of search
 * dimensions and a corresponding slide-in image preview.
 * @returns Dimensions section.
 */
export const DimensionsSection = (): JSX.Element => {
  const accordionKeys = Object.keys(ACCORDION);
  const { activeIndex, onSelectIndex } = useAutoCycle(accordionKeys);
  return (
    <StyledSection>
      <StyledContainer>
        <Stack direction={STACK_PROPS.DIRECTION.ROW} spacing={4} useFlexGap>
          <Stack flex={1} spacing={6} useFlexGap>
            <StyledSectionHeading component="h2">
              <div>Describe your research question.</div>
              <div>We search six dimensions.</div>
            </StyledSectionHeading>
            <StyledBox>
              {Object.entries(ACCORDION).map(([value, { details, title }]) => (
                <StyledAccordion
                  {...ACCORDION_PROPS}
                  key={value}
                  expanded={activeIndex === value}
                  onClick={() => onSelectIndex(value)}
                >
                  <AccordionSummary>{title}</AccordionSummary>
                  {details && <AccordionDetails>{details}</AccordionDetails>}
                </StyledAccordion>
              ))}
            </StyledBox>
          </Stack>
          <Stack flex={1} useFlexGap>
            {Object.entries(IMAGE).map(([value, src]) => (
              <Slide {...SLIDE_PROPS} key={value} in={activeIndex === value}>
                <StyledImageBox>
                  <StyledImage
                    alt={ACCORDION[value as keyof typeof ACCORDION].title}
                    src={src}
                  />
                </StyledImageBox>
              </Slide>
            ))}
          </Stack>
        </Stack>
      </StyledContainer>
    </StyledSection>
  );
};
