import { useLayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/hook";
import { ResearchView } from "@databiosphere/findable-ui/lib/views/ResearchView/researchView";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import Router from "next/router";
import { JSX, useEffect } from "react";
import { ROUTES } from "../../../routes/constants";
import { Hero } from "./components/Hero/hero";
import { Main } from "./components/Main/main";
import { Side } from "./components/Side/side";
import { StyledContainer, StyledGrid } from "./studyDetailView.styles";
import { Props } from "./types";

/**
 * Renders the study detail view.
 * @param props - Props.
 * @returns Study detail view.
 */
export const StudyDetailView = (props: Props): JSX.Element => {
  const { spacing } = useLayoutSpacing();
  const { state } = useChatState();

  const { study } = props;

  useEffect(() => {
    // Any new request in the chat will trigger a navigation to the research studies page,
    // where the user can view the results of their query.
    if (!state.status.loading) return;
    Router.push(ROUTES.RESEARCH_STUDIES);
  }, [state.status.loading]);

  return (
    <ResearchView>
      <StyledGrid {...spacing}>
        <StyledContainer maxWidth={false}>
          <Hero {...props} />
          <Main study={study} subpath={props.subpath} />
          <Side study={study} subpath={props.subpath} />
        </StyledContainer>
      </StyledGrid>
    </ResearchView>
  );
};
