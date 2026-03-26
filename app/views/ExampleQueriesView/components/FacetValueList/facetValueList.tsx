import { Stack } from "@mui/material";
import { JSX } from "react";
import { FacetValueGroup } from "../../constants";
import { QueryChip } from "../QueryChip/queryChip";

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
          <ul>
            {values.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
          {examples && examples.length > 0 && (
            <Stack
              direction="row"
              flexWrap="wrap"
              gap={1}
              sx={{ margin: "16px 0" }}
            >
              {examples.map(({ label: chipLabel, query }) => (
                <QueryChip key={chipLabel} label={chipLabel} query={query} />
              ))}
            </Stack>
          )}
        </div>
      ))}
    </>
  );
};
