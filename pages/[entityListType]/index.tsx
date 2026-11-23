import { getEntityConfig } from "@databiosphere/findable-ui/lib/config/utils";
import { getEntityService } from "@databiosphere/findable-ui/lib/hooks/useEntityService";
import { EXPLORE_MODE } from "@databiosphere/findable-ui/lib/hooks/useExploreMode/types";
import { seedDatabase } from "@databiosphere/findable-ui/lib/utils/seedDatabase";
import { ExploreView } from "@databiosphere/findable-ui/lib/views/ExploreView/exploreView";
import type { ExploreViewProps } from "@databiosphere/findable-ui/lib/views/ExploreView/types";
import { config } from "app/config/config";
import type {
  GetStaticPaths,
  GetStaticProps,
  GetStaticPropsContext,
} from "next";
import type { ParsedUrlQuery } from "querystring";
import type { JSX } from "react";

interface PageUrl extends ParsedUrlQuery {
  entityListType: string;
}

interface ListPageProps extends ExploreViewProps {
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
  // the component instance across the switch. On findable-ui v58 and earlier,
  // the explore state's tabValue lagged the page config during the switch and
  // a stale response was mapped with the other entity's mapper, crashing the
  // list (e.g. studies ⇄ platforms). From v61 each explore mode loads its
  // entity list through its own strategy, and from v63 ExploreView takes the
  // entity array directly. The key stays as a precaution until findable-ui
  // drives explore state from the page's entityListType across tab changes;
  // remove it then.
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
export const getStaticProps: GetStaticProps<ListPageProps> = async (
  context: GetStaticPropsContext
) => {
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
  props.data = (await fetchAllEntities(entityListType, undefined)).hits;

  return {
    props,
  };
};

export default IndexPage;
