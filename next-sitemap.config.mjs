/** @type {import('next-sitemap').IConfig} */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const SEPARATOR = ",";

const isProd = process.env.NEXT_PUBLIC_SITE_CONFIG === "ncpi-catalog-prod";

const siteMapConfig = {
  changefreq: "monthly",
  exclude: (process.env.SITEMAP_EXCLUDE ?? "").split(SEPARATOR),
  generateIndexSitemap: false,
  generateRobotsTxt: true,
  outDir: `./out${basePath}`,
  robotsTxtOptions: {
    policies: [
      {
        allow: isProd ? "/" : undefined,
        disallow: isProd ? "/chat" : "/",
        userAgent: "*",
      },
    ],
  },
  siteUrl: `${process.env.NEXT_PUBLIC_SITEMAP_DOMAIN}${basePath}`,
};

export default siteMapConfig;
