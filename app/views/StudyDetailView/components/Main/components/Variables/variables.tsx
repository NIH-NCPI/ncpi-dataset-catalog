import { JSX } from "react";
import { Props } from "./types";
import { Variables as VariablesComponent } from "../../../../../../components/Detail/components/Variables/variables";
import { buildVariables } from "../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";

/**
 * Renders the variables section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Variables section of the study detail view.
 */
export const Variables = ({ study, subpath }: Props): JSX.Element | null => {
  if (subpath !== "variables") return null;
  return <VariablesComponent {...buildVariables(study)} />;
};
