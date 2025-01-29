import { ANCHOR_TARGET } from "@databiosphere/findable-ui/lib/components/Links/common/entities";
import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import * as C from "../../../app/components/index";
import { GIT_HUB_REPO_URL } from "../../common/constants";
import {
  NCPI_CATALOG_CATEGORY_KEY,
  NCPI_CATALOG_CATEGORY_LABEL,
} from "../category";
import { platformsEntityConfig } from "./index/platformsEntityConfig";
import { studiesEntityConfig } from "./index/studiesEntityConfig";
import { exportConfig } from "./export/export";

const logoNcpi = "/images/logoNCPI.png";

// Template constants
const APP_TITLE = "NCPI Dataset Catalog";
const BROWSER_URL = "TODO";
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
            key: NCPI_CATALOG_CATEGORY_KEY.PLATFORM,
            label: NCPI_CATALOG_CATEGORY_LABEL.PLATFORM,
          },
          {
            key: NCPI_CATALOG_CATEGORY_KEY.TITLE,
            label: NCPI_CATALOG_CATEGORY_LABEL.TITLE,
          },
          {
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
            key: NCPI_CATALOG_CATEGORY_KEY.CONSENT_CODE,
            label: NCPI_CATALOG_CATEGORY_LABEL.CONSENT_CODE,
          },
        ],
      },
    ],
    key: "ncpi-catalog",
  },
  dataSource: {
    defaultListParams: {
      size: "25",
      sort: "entryId",
    },
    url: "https://service.nadove2.dev.singlecell.gi.ucsc.edu/",
  },
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
      navLinks: [],
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
            label: C.LabelIconMenuItem({ label: "Visit ncpi-acc.org" }),
            target: ANCHOR_TARGET.BLANK,
            url: PORTAL_URL,
          },
        ],
      ],
      searchEnabled: false,
      searchURL: ``,
      slogan: SLOGAN,
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
