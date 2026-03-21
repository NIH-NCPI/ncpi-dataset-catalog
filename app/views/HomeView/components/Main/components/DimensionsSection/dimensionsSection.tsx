import { AccordionDetails, AccordionSummary, Slide } from "@mui/material";
import { JSX } from "react";
import { StyledContainer } from "../Section/section.styles";
import { ACCORDION, IMAGE } from "./accordion";
import { ACCORDION_PROPS, SLIDE_PROPS } from "./constants";
import {
  StyledAccordion,
  StyledHeadline,
  StyledImage,
  StyledImageBox,
  StyledLeftBox,
  StyledRightBox,
  StyledSection,
  StyledSectionTitle,
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
        <StyledHeadline>
          <StyledSectionTitle component="h2">
            <span>Describe your research question.</span>
            <span>We search six dimensions.</span>
          </StyledSectionTitle>
        </StyledHeadline>
        <StyledLeftBox>
          {Object.entries(ACCORDION).map(([value, { details, title }]) => (
            <StyledAccordion
              {...ACCORDION_PROPS}
              key={value}
              expanded={activeIndex === value}
              onClick={() => onSelectIndex(value)}
            >
              <AccordionSummary>{title}</AccordionSummary>
              <AccordionDetails key={value}>{details}</AccordionDetails>
            </StyledAccordion>
          ))}
        </StyledLeftBox>
        <StyledRightBox>
          {/* Slide transitions will be driven by activeIndex when all images are added */}
          {Object.entries(IMAGE).map(([value, src]) => (
            <Slide {...SLIDE_PROPS} key={value} in={value === "0"}>
              <StyledImageBox>
                <StyledImage
                  alt={ACCORDION[value as keyof typeof ACCORDION].title}
                  src={src}
                />
              </StyledImageBox>
            </Slide>
          ))}
        </StyledRightBox>
      </StyledContainer>
    </StyledSection>
  );
};
