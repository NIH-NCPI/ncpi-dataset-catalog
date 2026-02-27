import { FluidPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/FluidPaper/fluidPaper";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Link, Typography } from "@mui/material";
import { JSX } from "react";
import { Props } from "./types";
import { StyledStack, VariableItem, VariableList } from "./variables.styles";

/**
 * Build a dbGaP variable page URL.
 * @param studyAccession - Study accession with version (e.g., "phs000007.v1.p1").
 * @param phvId - Variable PHV ID (e.g., "phv00481718.v2.p1").
 * @returns Full URL to the variable page on dbGaP.
 */
function buildDbGapVariableUrl(studyAccession: string, phvId: string): string {
  const phvNum = phvId.split(".")[0].replace("phv", "");
  return `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id=${studyAccession}&phv=${phvNum}`;
}

/**
 * Renders a list of variables grouped by category.
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
            <VariableList>
              {category.variables.map((variable) => (
                <VariableItem key={variable.id}>
                  <Typography
                    component="span"
                    variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}
                  >
                    {variable.name}
                    {variable.description && ` - ${variable.description}`}
                    {" ("}
                    <Link
                      href={buildDbGapVariableUrl(studyAccession, variable.id)}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {variable.id}
                    </Link>
                    {")"}
                  </Typography>
                </VariableItem>
              ))}
            </VariableList>
          )}
        </FluidPaper>
      ))}
    </StyledStack>
  );
};
