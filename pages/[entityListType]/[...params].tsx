import {
  AzulCatalogResponse,
  AzulEntitiesResponse,
  AzulEntityStaticResponse,
  AzulListParams,
} from "@databiosphere/findable-ui/lib/apis/azul/common/entities";
import {
  PARAMS_INDEX_TAB,
  PARAMS_INDEX_UUID,
} from "@databiosphere/findable-ui/lib/common/constants";
import {
  BackPageTabConfig,
  EntityConfig,
} from "@databiosphere/findable-ui/lib/config/entities";
import { getEntityConfig } from "@databiosphere/findable-ui/lib/config/utils";
import { fetchCatalog } from "@databiosphere/findable-ui/lib/entity/api/service";
import { getEntityService } from "@databiosphere/findable-ui/lib/hooks/useEntityService";
import { EXPLORE_MODE } from "@databiosphere/findable-ui/lib/hooks/useExploreMode/types";
import { EntityDetailView } from "@databiosphere/findable-ui/lib/views/EntityDetailView/entityDetailView";
import { NCPICatalogStudy } from "app/apis/catalog/ncpi-catalog/common/entities";
import { StudyJsonLd } from "app/components/Detail/components/StudyJsonLd/studyJsonLd";
import { config } from "app/config/config";
import {
  getBuildTimeEntities,
  getBuildTimeEntity,
  seedDatabase,
} from "app/utils/seedDatabase";
import { getStudyPageMeta } from "app/utils/studyTitles";
import { GetStaticPaths, GetStaticProps, GetStaticPropsContext } from "next";
import { ParsedUrlQuery } from "querystring";
import { JSX } from "react";

const setOfProcessedIds = new Set<string>();

interface StaticPath {
  params: PageUrl;
}

interface PageUrl extends ParsedUrlQuery {
  entityListType: string;
  params: string[];
}

export interface EntityDetailPageProps extends AzulEntityStaticResponse {
  browserURL?: string;
  entityListType: string;
  pageDescription?: string;
  pageTitle?: string;
}

/**
 * Entity detail view page.
 * @param props - Entity detail view page props.
 * @param props.browserURL - Browser URL.
 * @param props.data - Entity data.
 * @param props.entityListType - Entity list type.
 * @returns Entity detail view component.
 */
const EntityDetailPage = (props: EntityDetailPageProps): JSX.Element => {
  const { browserURL, data, entityListType } = props;
  if (!entityListType) return <></>;
  return (
    <>
      {entityListType === "studies" && browserURL && data && (
        <StudyJsonLd browserURL={browserURL} study={data as NCPICatalogStudy} />
      )}
      <EntityDetailView {...props} />
    </>
  );
};

/**
 * getStaticPaths - return the list of paths to prerender for each entity type and its tabs.
 * @returns Promise<GetStaticPaths<PageUrl>>.
 */
export const getStaticPaths: GetStaticPaths<PageUrl> = async () => {
  const appConfig = config();
  const { dataSource, entities } = appConfig;
  const { defaultParams } = dataSource;
  const { catalog: defaultCatalog } = defaultParams || {};

  const paths: StaticPath[] = [];

  for (const entityConfig of entities) {
    const { exploreMode } = entityConfig;
    // Process static paths.
    if (entityConfig.detail.staticLoad) {
      // Paths sourced from the build-time entity cache.
      await processSeededEntityPaths(entityConfig, paths);
      // Server-side fetch, server-side filtering.
      if (exploreMode === EXPLORE_MODE.SS_FETCH_SS_FILTERING) {
        // Fetch catalogs and generate a list of catalogs associated with the default catalog.
        const azulCatalogResponse = await fetchCatalog();
        const catalogs = getCatalogs(azulCatalogResponse, defaultCatalog);
        // Define the list params.
        const listParams = { size: "100" };
        // Fetch entities for each catalog and process the paths.
        for (const catalog of catalogs) {
          const entitiesResponse = await getEntities(
            entityConfig,
            catalog,
            listParams
          );
          processEntityPaths(entityConfig, entitiesResponse, paths);
        }
      }
    }
  }

  return {
    fallback: false,
    paths,
  };
};

export const getStaticProps: GetStaticProps<EntityDetailPageProps> = async ({
  params,
}: GetStaticPropsContext) => {
  const appConfig = config();
  const { browserURL, entities } = appConfig;
  const entityListType = (params as PageUrl).entityListType;
  const slug = (params as PageUrl).params;
  const entityConfig = getEntityConfig(entities, entityListType);
  const entityTab = getSlugPath(slug, PARAMS_INDEX_TAB);
  const entityId = getSlugPath(slug, PARAMS_INDEX_UUID);

  if (!entityConfig || !entityId) return { notFound: true };

  const studyMeta =
    entityListType === "studies" && entityId
      ? getStudyPageMeta(entityId, entityTab || undefined)
      : {};
  const props: EntityDetailPageProps = {
    browserURL,
    entityListType,
    ...studyMeta,
  };

  // Process entity props.
  await processEntityProps(entityConfig, entityTab, entityId, props);

  return {
    props,
  };
};

export default EntityDetailPage;

/**
 * Returns the catalog prefix for the given default catalog.
 * @param defaultCatalog - Default catalog.
 * @returns catalog prefix.
 */
function getCatalogPrefix(defaultCatalog: string): string {
  //eslint-disable-next-line sonarjs/slow-regex -- catalog numbers should be short and are not user provided
  return defaultCatalog.replace(/\d.*$/, ""); //TODO - are all catalog numbers less than a maximum length? could remove eslint ignore
}

/**
 * Returns the catalogs associated with the default catalog.
 * @param catalogResponse - Catalog response.
 * @param defaultCatalog - Default catalog.
 * @returns catalogs.
 */
function getCatalogs(
  catalogResponse: AzulCatalogResponse,
  defaultCatalog?: string
): string[] {
  const catalogs: string[] = [];
  if (!defaultCatalog) return catalogs;
  const catalogPrefix = getCatalogPrefix(defaultCatalog);
  for (const [catalog, { internal }] of Object.entries(
    catalogResponse.catalogs
  )) {
    if (internal) continue;
    if (catalog.startsWith(catalogPrefix)) {
      catalogs.push(catalog);
    }
  }
  return catalogs;
}

/**
 * Fetches entities response for the given entity config.
 * @param entityConfig - Entity config.
 * @param catalog - Catalog.
 * @param listParams - List params.
 * @returns entities response.
 */
async function getEntities(
  entityConfig: EntityConfig,
  catalog?: string,
  listParams?: AzulListParams
): Promise<AzulEntitiesResponse> {
  const { fetchAllEntities, path } = getEntityService(entityConfig, catalog);
  return await fetchAllEntities(path, undefined, catalog, listParams);
}

/**
 * Fetches the entity for the given entity ID.
 * @param entityConfig - Entity config.
 * @param entityId - Entity ID.
 * @returns entity response.
 */
async function getEntity(
  entityConfig: EntityConfig,
  entityId: string
): Promise<AzulEntityStaticResponse> {
  // Server-side fetch, client-side filtering: read the build-time entity
  // cache directly — the entity service for this mode (API_CF) does not
  // implement fetchEntityDetail and would throw.
  if (entityConfig.exploreMode === EXPLORE_MODE.SS_FETCH_CS_FILTERING) {
    return (await getBuildTimeEntity(
      entityConfig,
      entityId
    )) as AzulEntityStaticResponse;
  }
  const { fetchEntityDetail, path } = getEntityService(entityConfig, undefined);
  return await fetchEntityDetail(
    entityId,
    path,
    undefined,
    undefined,
    undefined,
    true
  );
}

/**
 * Returns the slug path for the given slug and slug index.
 * @param slug - Slug.
 * @param slugIndex - Slug index.
 * @returns path.
 */
function getSlugPath(slug: string[], slugIndex: number): string | undefined {
  return slug[slugIndex];
}

/**
 * Returns the list of tab routes for the given tab config.
 * @param tabs - Tab config.
 * @returns tab routes.
 */
function getTabRoutes(tabs: BackPageTabConfig[]): string[] {
  return tabs.map(({ route }) => route) ?? [];
}

/**
 * Processes the static paths for the given entity response.
 * @param entityConfig - Entity config.
 * @param entitiesResponse - Entities response.
 * @param paths - Static paths.
 */
function processEntityPaths(
  entityConfig: EntityConfig,
  entitiesResponse: Pick<AzulEntitiesResponse, "hits">,
  paths: StaticPath[]
): void {
  const { detail, route: entityListType } = entityConfig;
  const { tabs } = detail;
  const { hits: entities } = entitiesResponse;
  const tabRoutes = getTabRoutes(tabs);
  for (const entity of entities) {
    const entityId = entityConfig.getId?.(entity);
    if (!entityId) continue;
    // Skip the entity if it has already been processed.
    if (setOfProcessedIds.has(entityId)) continue;
    setOfProcessedIds.add(entityId);
    // Generate a path for each entity and each tab.
    for (const tabRoute of tabRoutes) {
      const params = [entityId, tabRoute];
      paths.push({
        params: {
          entityListType,
          params,
        },
      });
    }
  }
}

/**
 * Processes the entity props for the given entity page.
 * @param entityConfig - Entity config.
 * @param entityTab - Entity tab.
 * @param entityId - Entity ID.
 * @param props - Entity detail page props.
 */
async function processEntityProps(
  entityConfig: EntityConfig,
  entityTab = "",
  entityId: string,
  props: EntityDetailPageProps
): Promise<void> {
  const {
    detail: { staticLoad },
    exploreMode,
  } = entityConfig;
  // Early exit; return if the entity is not to be statically loaded.
  if (!staticLoad) return;
  // When the entity detail is to be fetched from API, we only do so for the first tab.
  if (exploreMode === EXPLORE_MODE.SS_FETCH_SS_FILTERING && entityTab) return;
  if (exploreMode === EXPLORE_MODE.CS_FETCH_CS_FILTERING) {
    // Seed database; this mode's detail fetch goes through the TSV entity
    // service, which reads the database internally. SS_FETCH_CS_FILTERING
    // details are read from the build-time entity cache — see getEntity.
    await seedDatabase(entityConfig);
  }
  // Fetch entity detail, either from database or API.
  const entityResponse = await getEntity(entityConfig, entityId);
  if (entityResponse) {
    props.data = entityResponse;
  }
}

/**
 * Processes static paths for entities whose paths are sourced from the
 * build-time entity cache: client-side fetch mode, and server-side fetch
 * with client-side filtering — see getBuildTimeEntities.
 * @param entityConfig - Entity config.
 * @param paths - Static paths.
 */
async function processSeededEntityPaths(
  entityConfig: EntityConfig,
  paths: StaticPath[]
): Promise<void> {
  const { exploreMode } = entityConfig;
  if (
    exploreMode !== EXPLORE_MODE.CS_FETCH_CS_FILTERING &&
    exploreMode !== EXPLORE_MODE.SS_FETCH_CS_FILTERING
  ) {
    return;
  }
  const hits = await getBuildTimeEntities(entityConfig);
  processEntityPaths(entityConfig, { hits }, paths);
}
