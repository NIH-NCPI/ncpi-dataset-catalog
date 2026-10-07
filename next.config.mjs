import nextMDX from "@next/mdx";

const withMDX = nextMDX({ extension: /\.mdx?$/ });

/** @type {import('next').NextConfig} */
const nextConfig = {
  agentRules: false,
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  experimental: {
    // The tsc CLI checker type-checks .next/dev/types, which clash with
    // .next/types after a `next dev` session; the API checker excludes them.
    useTypeScriptCli: false,
  },
  images: { unoptimized: true },
  output: "export",
  pageExtensions: ["md", "mdx", "ts", "tsx"],
  reactStrictMode: true,
  staticPageGenerationTimeout: 120,
  transpilePackages: ["@databiosphere/findable-ui"],
};

export default withMDX(nextConfig);
