import { ANCHOR_TARGET } from "@databiosphere/findable-ui/lib/components/Links/common/entities";
import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { VIEW_KIND } from "@databiosphere/findable-ui/lib/common/categories/views/types";
import * as C from "../../../app/components/index";
import { GIT_HUB_REPO_URL } from "../../common/constants";
import {
  NCPI_CATALOG_CATEGORY_KEY,
  NCPI_CATALOG_CATEGORY_LABEL,
} from "../category";
import { platformsEntityConfig } from "./index/platformsEntityConfig";
import { studiesEntityConfig } from "./index/studiesEntityConfig";
import { exportConfig } from "./export/export";
import { socialMedia } from "./socialMedia";
import { ROUTES } from "routes/constants";
import dataDictionary from "./dataDictionary/data-dictionary.json";
import { buildDataDictionary } from "app/viewModelBuilders/dataDictionaryMapper/dataDictionaryMapper";
import { TABLE_OPTIONS } from "app/viewModelBuilders/dataDictionaryMapper/tableOptions";
import { DataDictionaryConfig } from "@databiosphere/findable-ui/lib/common/entities";

const logoNcpi = "/images/logoNCPI.png";

// Template constants
const APP_TITLE = "NCPI Dataset Catalog";
const BROWSER_URL = "https://ncpi-data.dev.clevercanary.com";
const PORTAL_URL = "https://ncpi-acc.org"; // https://www.ncpi-acc.org/
const SLOGAN = "NIH Cloud Platform Interoperability Effort";

const config: SiteConfig = {
  analytics: {
    gtmAuth: "hQW1TUjhQSW9j0XTXzshYA", // GTM environment-specific
    gtmId: "GTM-55VGZN8",
    gtmPreview: "env-3",
  },
  appTitle: APP_TITLE,
  authentication: undefined,
  browserURL: BROWSER_URL,
  categoryGroupConfig: {
    categoryGroups: [
      {
        categoryConfigs: [
          {
            enableChartView: false,
            key: NCPI_CATALOG_CATEGORY_KEY.PLATFORM,
            label: NCPI_CATALOG_CATEGORY_LABEL.PLATFORM,
          },
          {
            enableChartView: false,
            key: NCPI_CATALOG_CATEGORY_KEY.TITLE,
            label: NCPI_CATALOG_CATEGORY_LABEL.TITLE,
          },
          {
            enableChartView: false,
            key: NCPI_CATALOG_CATEGORY_KEY.DB_GAP_ID,
            label: NCPI_CATALOG_CATEGORY_LABEL.DB_GAP_ID,
          },
          {
            key: NCPI_CATALOG_CATEGORY_KEY.FOCUS,
            label: NCPI_CATALOG_CATEGORY_LABEL.FOCUS,
          },
          {
            key: NCPI_CATALOG_CATEGORY_KEY.DATA_TYPE,
            label: NCPI_CATALOG_CATEGORY_LABEL.DATA_TYPE,
          },
          {
            key: NCPI_CATALOG_CATEGORY_KEY.STUDY_DESIGN,
            label: NCPI_CATALOG_CATEGORY_LABEL.STUDY_DESIGN,
          },
          {
            enableChartView: false,
            key: NCPI_CATALOG_CATEGORY_KEY.CONSENT_CODE,
            label: NCPI_CATALOG_CATEGORY_LABEL.CONSENT_CODE,
          },
          {
            key: NCPI_CATALOG_CATEGORY_KEY.PARTICIPANT_COUNT,
            label: NCPI_CATALOG_CATEGORY_LABEL.PARTICIPANT_COUNT,
            viewKind: VIEW_KIND.RANGE,
          },
        ],
      },
    ],
    key: "ncpi-catalog",
  },
  dataDictionaries: [
    {
      dataDictionary: buildDataDictionary(dataDictionary),
      path: "ncpi-data-dictionary",
      tableOptions: TABLE_OPTIONS,
    },
  ] as unknown as DataDictionaryConfig[],
  dataSource: {
    defaultListParams: {
      size: "25",
      sort: "entryId",
    },
    url: "https://service.nadove2.dev.singlecell.gi.ucsc.edu/",
  },
  enableEntitiesView: true,
  entities: [platformsEntityConfig, studiesEntityConfig],
  explorerTitle: "NCPI Dataset Catalog",
  export: exportConfig,
  exportToTerraUrl: "https://app.terra.bio",
  gitHubUrl: GIT_HUB_REPO_URL,
  layout: {
    footer: {
      Branding: C.Logo({
        alt: APP_TITLE,
        height: 36,
        link: PORTAL_URL,
        src: logoNcpi,
        target: ANCHOR_TARGET.BLANK,
      }),
      navLinks: [
        {
          label: "Feedback & Support",
          target: ANCHOR_TARGET.BLANK,
          url: "https://github.com/NIH-NCPI/ncpi-dataset-catalog/issues/new?template=feedback.md",
        },
      ],
      socials: socialMedia.socials,
      versionInfo: true,
    },
    header: {
      authenticationEnabled: false,
      logo: C.Logo({
        alt: APP_TITLE,
        height: 36,
        link: "/platforms",
        src: logoNcpi,
      }),
      navigation: [
        undefined,
        undefined,
        [
          {
            label: "Data Dictionary",
            url: ROUTES.DATA_DICTIONARY,
          },
          {
            label: C.LabelIconMenuItem({ label: "Visit ncpi-acc.org" }),
            target: ANCHOR_TARGET.BLANK,
            url: PORTAL_URL,
          },
        ],
      ],
      searchEnabled: false,
      searchURL: ``,
      slogan: SLOGAN,
      socialMedia: socialMedia,
    },
  },
  redirectRootToPath: "/platforms",
  themeOptions: {
    palette: {
      primary: {
        dark: "#003E76",
        main: "#035C94",
      },
    },
  },
};

export default config;
