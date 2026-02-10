import { FluidPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/FluidPaper/fluidPaper";
import {
  ANCHOR_TARGET,
  REL_ATTRIBUTE,
} from "@databiosphere/findable-ui/lib/components/Links/common/entities";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Link, Typography } from "@mui/material";
import React, { JSX } from "react";
import { StyledStack } from "./publications.styles";
import { formatCitation, getDOIUrl } from "./utils";
import { Props } from "./types";

/**
 * Renders a list of publication cards with title, citation, and DOI link.
 * @param props - Component props.
 * @param props.publications - Array of publications to display.
 * @returns Publications element.
 */
export const Publications = ({ publications }: Props): JSX.Element => {
  return (
    <StyledStack gap={4} useFlexGap>
      {publications.length > 0 ? (
        publications.map((publication, i) => (
          <FluidPaper key={`${publication.doi}-${i}`} elevation={0}>
            <Typography
              component="h4"
              variant={TYPOGRAPHY_PROPS.VARIANT.BODY_LARGE_500}
            >
              {publication.title}
            </Typography>
            <Typography
              color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
              variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400_2_LINES}
            >
              {formatCitation(publication)}
              {publication.citationCount > 0 &&
                ` Cited ${publication.citationCount.toLocaleString()} times.`}
              {publication.doi && (
                <>
                  {" "}
                  <Link
                    href={getDOIUrl(publication.doi)}
                    rel={REL_ATTRIBUTE.NO_OPENER_NO_REFERRER}
                    target={ANCHOR_TARGET.BLANK}
                  >
                    {getDOIUrl(publication.doi)}
                  </Link>
                </>
              )}
            </Typography>
          </FluidPaper>
        ))
      ) : (
        <FluidPaper elevation={0}>
          <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400_2_LINES}>
            No selected publications.
          </Typography>
        </FluidPaper>
      )}
    </StyledStack>
  );
};
