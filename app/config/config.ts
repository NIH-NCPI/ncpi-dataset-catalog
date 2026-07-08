import { setConfig } from "@databiosphere/findable-ui/lib/config/config";
import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import ncpiMapDev from "../../site-config/ncpi-catalog/dev/config";
import ncpiMapLocal from "../../site-config/ncpi-catalog/local/config";
import ncpiMapProd from "../../site-config/ncpi-catalog/prod/config";

const CONFIGS: { [k: string]: SiteConfig } = {
  "ncpi-catalog-dev": ncpiMapDev,
  "ncpi-catalog-local": ncpiMapLocal,
  "ncpi-catalog-prod": ncpiMapProd,
};

let appConfig: SiteConfig | null = null;

export const config = (): SiteConfig => {
  if (appConfig) {
    return appConfig;
  }

  const configKey = process.env.NEXT_PUBLIC_SITE_CONFIG;
  const siteConfig = configKey ? CONFIGS[configKey] : undefined;

  if (!siteConfig) {
    throw new Error(
      `Unknown site config "${configKey}" — set NEXT_PUBLIC_SITE_CONFIG to one of: ${Object.keys(
        CONFIGS
      ).join(", ")}`
    );
  }

  console.log(`Using app config ${configKey}`);
  appConfig = siteConfig;
  setConfig(appConfig); // Sets app config.
  return appConfig;
};
