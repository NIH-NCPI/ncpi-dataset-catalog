import {
  GetStaticPaths,
  GetStaticPathsResult,
  GetStaticProps,
  GetStaticPropsContext,
} from "next";
import { ParsedUrlQuery } from "querystring";
import { JSX } from "react";
import { RESEARCH_TYPE } from "../../../app/views/ResearchView/artifact/types";
import { StyledMain } from "../../../app/views/ResearchView/components/Main/main.styles";
import { seedDatabase } from "../../../app/utils/seedDatabase";
import { getEntities } from "../../[entityListType]/[...params]";
import { config } from "../../../app/config/config";
import { StudyDetailView } from "../../../app/views/StudyDetailView/studyDetailView";

interface Params extends ParsedUrlQuery {
  researchType: string;
  studyId: string;
}

interface Props {
  studyId: string;
}

interface Study {
  dbGapId: string;
}

/**
 * Gets static paths for the study detail view page.
 * @returns Static paths for the study detail view page.
 */
export const getStaticPaths: GetStaticPaths<Params> = async () => {
  const paths: GetStaticPathsResult<Params>["paths"] = [];

  for (const entityConfig of config().entities) {
    if (entityConfig.route !== "studies") continue;

    await seedDatabase(entityConfig.route, entityConfig);

    const entities = await getEntities(entityConfig);

    for (const entity of entities.hits) {
      const study = entity as Study;

      if (!study.dbGapId) continue;

      paths.push({
        params: {
          researchType: RESEARCH_TYPE.RESULTS,
          studyId: study.dbGapId,
        },
      });
    }
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
  const { studyId } = context.params || {};

  if (!studyId) return { notFound: true };

  return { props: { studyId } };
};

/**
 * Page component for the study detail view.
 * @param props - Props.
 * @param props.studyId - Study ID.
 * @returns Study detail view page.
 */
const Page = (props: Props): JSX.Element => {
  return <StudyDetailView {...props} />;
};

Page.Main = StyledMain;

export default Page;
