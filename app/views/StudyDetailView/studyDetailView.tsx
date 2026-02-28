import { JSX } from "react";
import { useLayoutSpacing } from "@databiosphere/findable-ui/lib/hooks/UseLayoutSpacing/hook";
import { StyledContainer, StyledGrid } from "./studyDetailView.styles";
import { Props } from "./types";
import { ResearchView } from "@databiosphere/findable-ui/lib/views/ResearchView/researchView";
import { getStudy } from "../../services/workflows/entities";
import { NCPICatalogStudy } from "../../apis/catalog/ncpi-catalog/common/entities";
import { Hero } from "./components/Hero/hero";
import { Main } from "./components/Main/main";
import { Side } from "./components/Side/side";

/**
 * Renders the study detail view.
 * @param props - Props.
 * @param props.studyId - Study ID.
 * @returns Study detail view.
 */
export const StudyDetailView = ({ studyId }: Props): JSX.Element => {
  const { spacing } = useLayoutSpacing();

  const study = getStudy<NCPICatalogStudy>(studyId);

  return (
    <ResearchView>
      <StyledGrid {...spacing}>
        <StyledContainer maxWidth={false}>
          <Hero study={study} />
          <Main study={study} />
          <Side study={study} />
        </StyledContainer>
      </StyledGrid>
    </ResearchView>
  );
};
