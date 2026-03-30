import { PromptMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { JSX } from "react";
import { FacetValueList } from "./components/FacetValueList/facetValueList";
import { StyledChips } from "./dimensionSection.styles";
import { DimensionSectionProps } from "./types";

/**
 * Renders a section for a single search dimension with description, example queries, and facet values.
 * @param props - Component props.
 * @param props.description - Dimension description.
 * @param props.examples - Example queries for the dimension.
 * @param props.explanation - Optional explanation text.
 * @param props.facetValues - Optional facet value groups.
 * @param props.title - Dimension title.
 * @returns Dimension section component.
 */
export const DimensionSection = ({
  description,
  examples,
  explanation,
  facetValues,
  title,
}: DimensionSectionProps): JSX.Element => {
  return (
    <section>
      <h2>{title}</h2>
      <p>{description}</p>
      {explanation && <p>{explanation}</p>}
      {/* Safe cast: Chips only reads message.suggestions. */}
      <StyledChips message={{ suggestions: examples } as PromptMessage} />
      {facetValues && <FacetValueList facetValues={facetValues} />}
    </section>
  );
};
