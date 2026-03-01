import { JSX } from "react";
import { useLayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/hook";
import { StyledGrid } from "./artifact.styles";
import { Props } from "./types";
import { ArtifactSelector } from "./selector/artifactSelector";
import { Form } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Form/form";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { useAdapter } from "@databiosphere/findable-ui/lib/views/ResearchView/adapter/useAdapter";
import { Tabs } from "../components/Tabs/tabs";

/**
 * Renders the artifact panel with tabs and content selector.
 * @param props - Component props.
 * @param props.researchType - Research type ("plan" or "datasets").
 * @returns Artifact component.
 */
export const Artifact = ({ researchType }: Props): JSX.Element => {
  const { actions } = useAdapter();
  const { state } = useChatState();
  const { spacing } = useLayoutSpacing();
  return (
    <StyledGrid {...spacing}>
      <Tabs researchType={researchType} />
      <Form actions={actions} status={state.status}>
        <ArtifactSelector researchType={researchType} state={state} />
      </Form>
    </StyledGrid>
  );
};
