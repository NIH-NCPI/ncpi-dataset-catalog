import { PromptMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { JSX } from "react";
import { FacetValueGroup } from "../../../../constants";
import { StyledChips } from "../../dimensionSection.styles";
import { StyledValueList } from "./facetValueList.styles";

interface FacetValueListProps {
  facetValues: FacetValueGroup[];
}

/**
 * Renders allowed facet values as bullet lists with optional example query chips.
 * @param props - Component props.
 * @param props.facetValues - Array of facet groups with labels, values, and optional examples.
 * @returns Facet value list component.
 */
export const FacetValueList = ({
  facetValues,
}: FacetValueListProps): JSX.Element => {
  return (
    <>
      {facetValues.map(({ examples, label, values }) => (
        <div key={label}>
          <h3>{label}</h3>
          {/* Safe cast: Chips only reads message.suggestions. */}
          {examples && (
            <StyledChips message={{ suggestions: examples } as PromptMessage} />
          )}
          <p>Available options:</p>
          <StyledValueList>
            {values.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </StyledValueList>
        </div>
      ))}
    </>
  );
};
