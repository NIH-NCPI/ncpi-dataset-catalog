import { JSX } from "react";
import { Props } from "./types";
import { StyledPublications } from "./selectedPublications.styles";
import { RoundedPaper } from "@databiosphere/findable-ui/lib/components/common/Paper/components/RoundedPaper/roundedPaper";

/**
 * Renders the selected publications section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Selected publications section of the study detail view.
 */
export const SelectedPublications = ({
  study,
  subpath,
}: Props): JSX.Element | null => {
  if (subpath !== "selected-publications") return null;
  return (
    <StyledPublications
      Paper={RoundedPaper}
      publications={study.publications ?? []}
    />
  );
};
