import fs from "fs";

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
import { NCPICatalogStudy } from "../../../app/apis/catalog/ncpi-catalog/common/entities";

const STUDIES_PATH = "catalog/ncpi-platform-studies.json";

interface Params extends ParsedUrlQuery {
  researchType: string;
  studyParams: string[];
}

interface Props {
  researchType: string;
  studyId: string;
  subpath: string;
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
          studyParams: [study.dbGapId, "selected-publications"],
        },
      });

      // Variables subpath "variables".
      paths.push({
        params: {
          researchType: RESEARCH_TYPE.RESULTS,
          studyParams: [study.dbGapId, "variables"],
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
  const { researchType, studyParams } = context.params || {};

  if (!researchType) return { notFound: true };
  if (!studyParams || studyParams.length === 0) return { notFound: true };

  const [studyId, subpath = ""] = studyParams;

  // Look up study title for OG meta tags.
  let pageTitle = studyId;
  try {
    const studies = JSON.parse(fs.readFileSync(STUDIES_PATH, "utf-8"));
    const study = Object.values(studies).find(
      (s) => (s as { dbGapId: string }).dbGapId === studyId
    ) as { title?: string } | undefined;
    if (study?.title) {
      pageTitle = `${studyId} — ${study.title}`;
    }
  } catch {
    // Fall back to studyId if catalog file is unavailable.
  }

  return { props: { pageTitle, researchType, studyId, subpath } };
};

/**
 * Page component for the study detail view.
 * @param props - Props.
 * @param props.researchType - Research type for the study detail view ("results").
 * @param props.studyId - Study ID.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Study detail view page.
 */
const Page = (props: Props): JSX.Element => {
  return <StudyDetailView {...props} />;
};

Page.Main = StyledMain;

export default Page;
