import { FluidPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/FluidPaper/fluidPaper";
import { IdentityCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/identityCell";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Link, Typography } from "@mui/material";
import { JSX } from "react";
import { buildVariableIdentityChips } from "../../../../viewModelBuilders/catalog/ncpi-catalog/common/variableIdentity/utils";
import type { Props } from "./types";
import { buildDbGapVariableUrl } from "./utils";
import { StyledStack, VariableRow, VariableRows } from "./variables.styles";

/**
 * Renders variables grouped by category: one card per category, with a row per
 * variable (name chip, description, dbGaP link).
 * @param props - Component props.
 * @param props.studyAccession - Study accession with version for building dbGaP links.
 * @param props.variableSummary - Variable summary data.
 * @returns Variables element.
 */
export const Variables = ({
  studyAccession,
  variableSummary,
}: Props): JSX.Element => {
  if (!variableSummary || variableSummary.categories.length === 0) {
    return (
      <StyledStack gap={4} useFlexGap>
        <FluidPaper elevation={0}>
          <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400_2_LINES}>
            No variable data available.
          </Typography>
        </FluidPaper>
      </StyledStack>
    );
  }

  const { categories } = variableSummary;

  return (
    <StyledStack gap={4} useFlexGap>
      {categories.map((category) => (
        <FluidPaper key={category.categoryId} elevation={0}>
          <Typography
            component="h4"
            variant={TYPOGRAPHY_PROPS.VARIANT.BODY_LARGE_500}
          >
            {category.categoryName} ({category.totalCount.toLocaleString()})
          </Typography>

          {category.variables && category.variables.length > 0 && (
            <VariableRows>
              {category.variables.map((variable) => (
                <VariableRow key={variable.id}>
                  <IdentityCell
                    chips={buildVariableIdentityChips(variable.name)}
                  />
                  <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}>
                    {variable.description}
                  </Typography>
                  <Link
                    href={buildDbGapVariableUrl(studyAccession, variable.id)}
                    rel="noopener noreferrer"
                    target="_blank"
                    variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}
                  >
                    {variable.id}
                  </Link>
                </VariableRow>
              ))}
            </VariableRows>
          )}
        </FluidPaper>
      ))}
    </StyledStack>
  );
};
