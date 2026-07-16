import { JSX } from "react";
import { Variables as VariablesComponent } from "../../../../../../components/Detail/components/Variables/variables";
import { buildVariables } from "../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import { STUDY_DETAIL_SUBPATH } from "../../../../constants";
import { Props } from "./types";

/**
 * Renders the variables section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Variables section of the study detail view.
 */
export const Variables = ({ study, subpath }: Props): JSX.Element | null => {
  if (subpath !== STUDY_DETAIL_SUBPATH.VARIABLES) return null;
  return <VariablesComponent {...buildVariables(study)} />;
};
