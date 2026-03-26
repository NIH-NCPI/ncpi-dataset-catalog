import { Chip, Stack, Typography } from "@mui/material";
import { JSX } from "react";
import { StyledSection } from "./facetValueList.styles";

interface FacetValueListProps {
  facetValues: { label: string; values: string[] }[];
}

/**
 * Renders display-only lists of allowed facet values.
 * @param props - Component props.
 * @param props.facetValues - Array of facet groups with labels and values.
 * @returns Facet value list component.
 */
export const FacetValueList = ({
  facetValues,
}: FacetValueListProps): JSX.Element => {
  return (
    <StyledSection>
      {facetValues.map(({ label, values }) => (
        <div key={label}>
          <Typography component="h4" variant="body-large-500">
            {label}
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {values.map((value) => (
              <Chip key={value} label={value} size="small" variant="outlined" />
            ))}
          </Stack>
        </div>
      ))}
    </StyledSection>
  );
};
