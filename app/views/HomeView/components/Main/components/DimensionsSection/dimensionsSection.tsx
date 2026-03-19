import { AccordionDetails, AccordionSummary, Slide } from "@mui/material";
import { JSX } from "react";
import { SectionTitle, StyledContainer } from "../Section/section.styles";
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
} from "./dimensionsSection.styles";
import { useAutoCycle } from "./hooks/UseAutoCycle/hook";

/**
 * Renders the dimensions section with an auto-cycling accordion of search
 * dimensions and a corresponding slide-in image preview.
 * @returns Dimensions section.
 */
export const DimensionsSection = (): JSX.Element => {
  const accordionKeys = Object.keys(ACCORDION);
  const { onSelectIndex } = useAutoCycle(accordionKeys);
  const activeIndex = "0";
  return (
    <StyledSection>
      <StyledContainer>
        <StyledHeadline>
          <SectionTitle component="h2">
            <div>Describe your research question.</div>
            <div>We search six dimensions.</div>
          </SectionTitle>
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
        </StyledRightBox>
      </StyledContainer>
    </StyledSection>
  );
};
