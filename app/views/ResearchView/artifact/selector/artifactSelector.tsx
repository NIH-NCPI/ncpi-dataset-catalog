import { JSX } from "react";
import { RESEARCH_TYPE } from "../types";
import { Props } from "./types";
import { Results } from "../../components/Main/components/Results/results";

/**
 * Selects the appropriate artifact view based on research type.
 * @param props - Component props.
 * @param props.researchType - Artifact view type "plan" or "results".
 * @param props.state - Chat state.
 * @returns The selected view component.
 */
export const ArtifactSelector = ({
  researchType,
  state,
}: Props): JSX.Element | null => {
  switch (researchType) {
    case RESEARCH_TYPE.RESULTS:
      return <Results state={state} />;
    case RESEARCH_TYPE.PLAN:
      return null;
  }
};
