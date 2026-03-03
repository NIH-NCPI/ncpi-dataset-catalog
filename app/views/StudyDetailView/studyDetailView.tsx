import { JSX, useEffect } from "react";
import { useLayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/hook";
import { StyledContainer, StyledGrid } from "./studyDetailView.styles";
import { Props } from "./types";
import { ResearchView } from "@databiosphere/findable-ui/lib/views/ResearchView/researchView";
import { getStudy } from "../../services/workflows/entities";
import { NCPICatalogStudy } from "../../apis/catalog/ncpi-catalog/common/entities";
import { Hero } from "./components/Hero/hero";
import { Main } from "./components/Main/main";
import { Side } from "./components/Side/side";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import Router from "next/router";
import { ROUTES } from "../../../routes/constants";

/**
 * Renders the study detail view.
 * @param props - Props.
 * @returns Study detail view.
 */
export const StudyDetailView = (props: Props): JSX.Element => {
  const { spacing } = useLayoutSpacing();
  const { state } = useChatState();

  const study = getStudy<NCPICatalogStudy>(props.studyId);

  useEffect(() => {
    // Any new request in the chat will trigger a navigation to the research datasets page,
    // where the user can view the results of their query.
    if (!state.status.loading) return;
    Router.push(ROUTES.RESEARCH_DATASETS);
  }, [state.status.loading]);

  return (
    <ResearchView>
      <StyledGrid {...spacing}>
        <StyledContainer maxWidth={false}>
          <Hero study={study} {...props} />
          <Main study={study} subpath={props.subpath} />
          <Side study={study} subpath={props.subpath} />
        </StyledContainer>
      </StyledGrid>
    </ResearchView>
  );
};
