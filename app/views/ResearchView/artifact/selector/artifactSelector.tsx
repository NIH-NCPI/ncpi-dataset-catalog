import { JSX } from "react";
import { RESEARCH_TYPE } from "../types";
import { Props } from "./types";
import { Datasets } from "../../ui/Datasets/datasets";

/**
 * Selects the appropriate artifact view based on research type.
 * @param props - Component props.
 * @param props.researchType - Artifact view type "plan" or "datasets".
 * @param props.state - Chat state.
 * @returns The selected view component.
 */
export const ArtifactSelector = ({
  researchType,
  state,
}: Props): JSX.Element | null => {
  switch (researchType) {
    case RESEARCH_TYPE.DATASETS:
      return <Datasets state={state} />;
    case RESEARCH_TYPE.PLAN:
      return null;
  }
};
