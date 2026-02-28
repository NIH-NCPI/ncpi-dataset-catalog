import { GetStaticPaths, GetStaticPathsResult, GetStaticProps } from "next";
import { ParsedUrlQuery } from "querystring";
import { JSX } from "react";
import { RESEARCH_TYPE } from "../../../app/views/ResearchView/artifact/types";
import { StyledMain } from "../../../app/views/ResearchView/components/Main/main.styles";
import { seedDatabase } from "../../../app/utils/seedDatabase";
import { getEntities } from "../../[entityListType]/[...params]";
import { config } from "../../../app/config/config";

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
          researchType: RESEARCH_TYPE.DATASETS,
          studyId: study.dbGapId,
        },
      });
    }
  }

  return { fallback: false, paths };
};

export const getStaticProps: GetStaticProps<Props, Params> = async ({
  params,
}) => {
  const { studyId } = params || {};

  if (!studyId) return { notFound: true };

  return { props: { studyId } };
};

const Page = ({ studyId }: Props): JSX.Element => {
  return <div>Study: {studyId}</div>;
};

Page.Main = StyledMain;

export default Page;
