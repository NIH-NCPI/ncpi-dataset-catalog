import { AzulEntitiesStaticResponse } from "@databiosphere/findable-ui/lib/apis/azul/common/entities";
import { Main as DXMain } from "@databiosphere/findable-ui/lib/components/Layout/components/Main/main.styles";
import { getEntityConfig } from "@databiosphere/findable-ui/lib/config/utils";
import { getEntityService } from "@databiosphere/findable-ui/lib/hooks/useEntityService";
import { EXPLORE_MODE } from "@databiosphere/findable-ui/lib/hooks/useExploreMode/types";
import { seedDatabase } from "@databiosphere/findable-ui/lib/utils/seedDatabase";
import { ExploreView } from "@databiosphere/findable-ui/lib/views/ExploreView/exploreView";
import { config } from "app/config/config";
import { GetStaticPaths, GetStaticProps, GetStaticPropsContext } from "next";
import { ParsedUrlQuery } from "querystring";
import { JSX } from "react";

interface PageUrl extends ParsedUrlQuery {
  entityListType: string;
}

interface ListPageProps extends AzulEntitiesStaticResponse {
  entityListType: string;
  pageTitle?: string;
}

/**
 * Explore view page.
 * @param props - Explore view page props.
 * @param props.entityListType - Entity list type.
 * @returns Explore view component.
 */
const IndexPage = ({
  entityListType,
  ...props
}: ListPageProps): JSX.Element => {
  if (!entityListType) return <></>;
  // Key by entity type so switching list tabs remounts ExploreView. Both list
  // routes render this same page component, so without the key React reuses
  // the component instance and useEntityList's fetched response survives the
  // switch; during the transition the explore state's tabValue lags the page
  // config, and the stale response gets mapped with the other entity's
  // mapper — crashing the list (e.g. studies ⇄ platforms).
  return (
    <ExploreView
      key={entityListType}
      entityListType={entityListType}
      {...props}
    />
  );
};

/**
 * Build the list of paths to be built statically.
 * @returns static paths.
 */
export const getStaticPaths: GetStaticPaths = async () => {
  const appConfig = config();
  const entities = appConfig.entities;
  const paths = entities.map((entity) => ({
    params: {
      entityListType: entity.route,
    },
  }));
  return {
    fallback: false,
    paths,
  };
};

/**
 * Build the set of props for pre-rendering of page.
 * @param context - Object containing values related to the current context.
 * @returns static props.
 */
export const getStaticProps: GetStaticProps<
  AzulEntitiesStaticResponse
> = async (context: GetStaticPropsContext) => {
  const appConfig = config();
  const { entityListType } = context.params as PageUrl;
  const { entities } = appConfig;
  const entityConfig = getEntityConfig(entities, entityListType);
  const { exploreMode, label } = entityConfig;
  const { fetchAllEntities } = getEntityService(entityConfig, undefined); // Determine the type of fetch, either from an API endpoint or a TSV.

  let pageTitle;
  if (typeof label === "string") {
    pageTitle = label;
  }

  const props: ListPageProps = { entityListType, pageTitle };

  // Seed database. findable-ui's seedDatabase seeds mapped entities, and the
  // client maps them again before dispatching them to explore state. That is
  // safe only while the entity mapper gives the same result when run twice.
  if (exploreMode === EXPLORE_MODE.CS_FETCH_CS_FILTERING) {
    await seedDatabase(entityListType, entityConfig);
  } else {
    // Entities are fetched server-side.
    return { props };
  }

  // Entities are read from the database seeded above from the static-load file.
  props.data = await fetchAllEntities(entityListType, undefined);

  return {
    props,
  };
};

IndexPage.Main = DXMain;

export default IndexPage;
