import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import devConfig from "../dev/config";

const config: SiteConfig = {
  ...devConfig,
  // Ternary required: devConfig.ai is typed as AiConfig | undefined,
  // so TS needs the guard to narrow before spreading.
  ai: devConfig.ai
    ? {
        ...devConfig.ai,
        url: "https://prejcyhpmp.us-east-1.awsapprunner.com/search",
      }
    : undefined,
  browserURL: "https://ncpi-data.org",
};

// Update gtmAuth for the prod environment lookup.
if (config.analytics) {
  const analytics = { ...config.analytics };
  analytics.gtmAuth = "fMpsUBfsBk6PX_2YnVY64g";
  analytics.gtmPreview = "env-1";
  config.analytics = analytics;
}

export default config;
