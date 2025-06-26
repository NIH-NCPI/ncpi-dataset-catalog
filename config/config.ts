import { setConfig } from "@databiosphere/findable-ui/lib/config/config";
import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import portalDev from "../site-config/ncpi-catalog/dev/config";
import portalProd from "../site-config/ncpi-catalog/prod/config";

const CONFIGS: { [k: string]: SiteConfig } = {
  "ncpi-catalog-dev": portalDev,
  "ncpi-catalog-prod": portalProd,
};

let appConfig: SiteConfig | null = null;

export const config = (): SiteConfig => {
  if (appConfig) {
    return appConfig;
  }

  const siteConfig = process.env.NEXT_PUBLIC_SITE_CONFIG;

  if (!siteConfig) {
    console.error(`Config not found. config: ${siteConfig}`);
  }

  appConfig = CONFIGS[siteConfig as string];

  if (!appConfig) {
    console.error(`No app config was found for the config: ${siteConfig}`);
  } else {
    console.log(`Using app config ${siteConfig}`);
  }

  setConfig(appConfig); // Sets app config.
  return appConfig;
};
