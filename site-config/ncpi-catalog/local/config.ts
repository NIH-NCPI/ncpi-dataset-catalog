import { SiteConfig } from "@databiosphere/findable-ui/lib/config/entities";
import devConfig from "../dev/config";

const config: SiteConfig = {
  ...devConfig,
  // Ternary required: devConfig.ai is typed as AiConfig | undefined,
  // so TS needs the guard to narrow before spreading.
  ai: devConfig.ai
    ? {
        ...devConfig.ai,
        url: "http://localhost:8000/search",
      }
    : undefined,
  // Local development must not report analytics to the dev GTM container.
  analytics: undefined,
  browserURL: "http://localhost:3000",
};

export default config;
