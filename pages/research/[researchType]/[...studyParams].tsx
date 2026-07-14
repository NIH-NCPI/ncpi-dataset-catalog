import { getEntityConfig } from "@databiosphere/findable-ui/lib/config/utils";
import {
  GetStaticPaths,
  GetStaticPathsResult,
  GetStaticProps,
  GetStaticPropsContext,
} from "next";
import { ParsedUrlQuery } from "querystring";
import { JSX } from "react";
import { NCPICatalogStudy } from "../../../app/apis/catalog/ncpi-catalog/common/entities";
import { config } from "../../../app/config/config";
import {
  getBuildTimeEntities,
  getBuildTimeEntity,
} from "../../../app/utils/seedDatabase";
import { sliceStudyBySubpath } from "../../../app/utils/studyDetailSlice";
import { getStudyPageMeta } from "../../../app/utils/studyTitles";
import { RESEARCH_TYPE } from "../../../app/views/ResearchView/artifact/types";
import { StyledMain } from "../../../app/views/ResearchView/components/Main/main.styles";
import { STUDY_DETAIL_SUBPATH } from "../../../app/views/StudyDetailView/constants";
import { StudyDetailView } from "../../../app/views/StudyDetailView/studyDetailView";
import type { Props as StudyDetailViewProps } from "../../../app/views/StudyDetailView/types";

const STUDIES_ROUTE = "studies";

interface Params extends ParsedUrlQuery {
  researchType: string;
  studyParams: string[];
}

interface Props extends StudyDetailViewProps {
  pageDescription?: string;
  pageTitle?: string;
}

/**
 * Gets static paths for the study detail view page.
 * @returns Static paths for the study detail view page.
 */
export const getStaticPaths: GetStaticPaths<Params> = async () => {
  const paths: GetStaticPathsResult<Params>["paths"] = [];

  const entityConfig = getEntityConfig(config().entities, STUDIES_ROUTE);
  const entities = await getBuildTimeEntities(entityConfig);

  for (const entity of entities) {
    const study = entity as NCPICatalogStudy;

    if (!study.dbGapId) continue;

    // Overview subpath "".
    paths.push({
      params: {
        researchType: RESEARCH_TYPE.RESULTS,
        studyParams: [study.dbGapId],
      },
    });

    // Selected publications subpath "selected-publications".
    paths.push({
      params: {
        researchType: RESEARCH_TYPE.RESULTS,
        studyParams: [
          study.dbGapId,
          STUDY_DETAIL_SUBPATH.SELECTED_PUBLICATIONS,
        ],
      },
    });

    // Variables subpath "variables".
    paths.push({
      params: {
        researchType: RESEARCH_TYPE.RESULTS,
        studyParams: [study.dbGapId, STUDY_DETAIL_SUBPATH.VARIABLES],
      },
    });
  }

  return { fallback: false, paths };
};

/**
 * Gets static props for the study detail view page.
 * @param context - GetStaticProps context.
 * @returns Static props for the study detail view page.
 */
export const getStaticProps: GetStaticProps<Props, Params> = async (
  context: GetStaticPropsContext<Params>
) => {
  const { researchType, studyParams } = context.params || {};

  if (!researchType) return { notFound: true };
  if (!studyParams || studyParams.length === 0) return { notFound: true };

  const [studyId, subpath = STUDY_DETAIL_SUBPATH.OVERVIEW] = studyParams;

  const entityConfig = getEntityConfig(config().entities, STUDIES_ROUTE);

  const study = await getBuildTimeEntity<NCPICatalogStudy>(
    entityConfig,
    studyId
  );

  if (!study) return { notFound: true };

  return {
    props: {
      ...getStudyPageMeta(studyId, subpath || undefined),
      publicationsCount: study.publications.length,
      researchType,
      study: sliceStudyBySubpath(study, subpath),
      subpath,
      variablesCount: study.variableSummary?.totalVariables ?? 0,
    },
  };
};

/**
 * Page component for the study detail view.
 * @param props - Props.
 * @param props.publicationsCount - Count of the study's publications (survives slicing for the Hero tab label).
 * @param props.researchType - Research type for the study detail view ("results").
 * @param props.study - Study, sliced for the subpath.
 * @param props.subpath - Subpath for the study detail view.
 * @param props.variablesCount - Count of the study's variables (survives slicing for the Hero tab label).
 * @returns Study detail view page.
 */
const Page = (props: Props): JSX.Element => {
  return <StudyDetailView {...props} />;
};

Page.Main = StyledMain;

export default Page;
