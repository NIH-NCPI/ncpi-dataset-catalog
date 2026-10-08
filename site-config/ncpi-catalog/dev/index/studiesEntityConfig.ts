import {
  ComponentConfig,
  EntityConfig,
  ListConfig,
  SORT_DIRECTION,
} from "@databiosphere/findable-ui/lib/config/entities";
import { EXPLORE_MODE } from "@databiosphere/findable-ui/lib/hooks/useExploreMode/types";
import { NCPICatalogStudy } from "../../../../app/apis/catalog/ncpi-catalog/common/entities";
import {
  getStudyId,
  getTitle,
  NCPIStudyInputMapper,
} from "../../../../app/apis/catalog/ncpi-catalog/common/utils";
import * as C from "../../../../app/components";
import * as V from "../../../../app/viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import {
  NCPI_CATALOG_CATEGORY_KEY,
  NCPI_CATALOG_CATEGORY_LABEL,
} from "../../category";
import { mainColumn } from "../detail/study/overviewMainColumn";
import { sideColumn } from "../detail/study/overviewSideColumn";
import { publicationsMainColumn } from "../detail/study/publicationsMainColumn";
import { top } from "../detail/study/top";
import { variablesMainColumn } from "../detail/study/variablesMainColumn";

// Runtime data source for the studies list (SS_FETCH_CS_FILTERING).
// scripts/sync-api.sh copies it from catalog/ into public/api/, which Next then
// includes in the export.
const STUDIES_LIST_API_PATH = "/api/ncpi-platform-studies.json";

// Settings for columns that are always hidden (also listed in
// tableOptions.initialState.columnVisibility).
const ALWAYS_HIDDEN_COLUMN = { enableHiding: false, enableSorting: false };

/**
 * Entity config object responsible for config related to the /studies route.
 */
export const studiesEntityConfig: EntityConfig<NCPICatalogStudy> = {
  apiPath: STUDIES_LIST_API_PATH,
  detail: {
    detailOverviews: ["Overview"],
    staticLoad: true,
    tabs: [
      {
        label: "Overview",
        mainColumn: mainColumn,
        route: "",
        sideColumn: sideColumn,
      },
      {
        label: "Selected Publications",
        mainColumn: publicationsMainColumn,
        route: "selected-publications",
      },
      {
        label: "Variables",
        mainColumn: variablesMainColumn,
        route: "variables",
      },
    ],
    top: top,
  },
  entityMapper: NCPIStudyInputMapper,
  exploreMode: EXPLORE_MODE.SS_FETCH_CS_FILTERING,
  getId: getStudyId,
  getTitle: getTitle,
  hideTabs: true,
  label: "Studies",
  list: {
    columns: [
      {
        columnPinned: true,
        componentConfig: {
          component: C.IdentityCell,
          viewBuilder: V.buildStudyIdentity,
        } as ComponentConfig<typeof C.IdentityCell>,
        header: NCPI_CATALOG_CATEGORY_LABEL.TITLE,
        id: NCPI_CATALOG_CATEGORY_KEY.TITLE,
        width: { max: "1.5fr", min: "340px" },
      },
      // dbGaP Id, Platform and Consent Code render as chips in the Study
      // column. Their columns stay, always hidden, because client-side facets
      // and the table download are both built from the table's columns. Their
      // cell components never render; ColumnConfig requires one.
      {
        componentConfig: {
          component: C.BasicCell,
          viewBuilder: V.buildDbGapId,
        } as ComponentConfig<typeof C.BasicCell>,
        ...ALWAYS_HIDDEN_COLUMN,
        header: NCPI_CATALOG_CATEGORY_LABEL.DB_GAP_ID,
        id: NCPI_CATALOG_CATEGORY_KEY.DB_GAP_ID,
        width: { max: "1.24fr", min: "124px" },
      },
      {
        componentConfig: {
          component: C.NTagCell,
          viewBuilder: V.buildPlatforms,
        } as ComponentConfig<typeof C.NTagCell>,
        ...ALWAYS_HIDDEN_COLUMN,
        header: NCPI_CATALOG_CATEGORY_LABEL.PLATFORM,
        id: NCPI_CATALOG_CATEGORY_KEY.PLATFORM,
        width: { max: "1fr", min: "100px" },
      },
      {
        componentConfig: {
          component: C.ConsentCodesCell,
          viewBuilder: V.buildConsentCodes,
        } as ComponentConfig<typeof C.ConsentCodesCell>,
        ...ALWAYS_HIDDEN_COLUMN,
        header: NCPI_CATALOG_CATEGORY_LABEL.CONSENT_CODE,
        id: NCPI_CATALOG_CATEGORY_KEY.CONSENT_CODE,
        width: { max: "1.6fr", min: "160px" },
      },
      {
        componentConfig: {
          component: C.BasicCell,
          viewBuilder: V.buildFocus,
        } as ComponentConfig<typeof C.BasicCell>,
        header: NCPI_CATALOG_CATEGORY_LABEL.FOCUS,
        id: NCPI_CATALOG_CATEGORY_KEY.FOCUS,
        width: { max: "1.6fr", min: "160px" },
      },
      {
        componentConfig: {
          component: C.NTagCell,
          viewBuilder: V.buildDataTypes,
        } as ComponentConfig<typeof C.NTagCell>,
        header: NCPI_CATALOG_CATEGORY_LABEL.DATA_TYPE,
        id: NCPI_CATALOG_CATEGORY_KEY.DATA_TYPE,
        width: { max: "1.6fr", min: "160px" },
      },
      {
        componentConfig: {
          component: C.NTagCell,
          viewBuilder: V.buildStudyDesigns,
        } as ComponentConfig<typeof C.NTagCell>,
        header: NCPI_CATALOG_CATEGORY_LABEL.STUDY_DESIGN,
        id: NCPI_CATALOG_CATEGORY_KEY.STUDY_DESIGN,
        width: { max: "1.6fr", min: "160px" },
      },
      {
        componentConfig: {
          component: C.BasicCell,
          viewBuilder: V.buildParticipantCount,
        } as ComponentConfig<typeof C.BasicCell>,
        filterFn: "inNumberRange",
        header: NCPI_CATALOG_CATEGORY_LABEL.PARTICIPANT_COUNT,
        id: NCPI_CATALOG_CATEGORY_KEY.PARTICIPANT_COUNT,
        width: { max: "1.16fr", min: "116px" },
      },
    ],
    tableOptions: {
      downloadFilename: "studies",
      enableTableDownload: true,
      initialState: {
        columnVisibility: {
          [NCPI_CATALOG_CATEGORY_KEY.CONSENT_CODE]: false,
          [NCPI_CATALOG_CATEGORY_KEY.DB_GAP_ID]: false,
          [NCPI_CATALOG_CATEGORY_KEY.PLATFORM]: false,
        },
        sorting: [
          {
            desc: SORT_DIRECTION.ASCENDING,
            id: NCPI_CATALOG_CATEGORY_KEY.TITLE,
          },
        ],
      },
    },
  } as ListConfig<NCPICatalogStudy>,
  listView: {
    disablePagination: true,
  },
  route: "studies",
  staticLoadFile: "catalog/ncpi-platform-studies.json",
  ui: { enableTabs: true },
};
