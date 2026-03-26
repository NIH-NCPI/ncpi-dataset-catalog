import { Stack } from "@mui/material";
import { JSX } from "react";
import { Dimension } from "../../constants";
import { FacetValueList } from "../FacetValueList/facetValueList";
import { QueryChip } from "../QueryChip/queryChip";

interface DimensionSectionProps {
  dimension: Dimension;
}

/**
 * Renders a section for a single search dimension with description, example queries, and facet values.
 * @param props - Component props.
 * @param props.dimension - Dimension configuration.
 * @returns Dimension section component.
 */
export const DimensionSection = ({
  dimension,
}: DimensionSectionProps): JSX.Element => {
  const { description, examples, explanation, facetValues, title } = dimension;
  return (
    <section>
      <h2>{title}</h2>
      <p>{description}</p>
      {explanation && <p>{explanation}</p>}
      <Stack direction="row" flexWrap="wrap" gap={1} sx={{ margin: "16px 0" }}>
        {examples.map(({ label, query }) => (
          <QueryChip key={label} label={label} query={query} />
        ))}
      </Stack>
      {facetValues && <FacetValueList facetValues={facetValues} />}
    </section>
  );
};
