import nextMDX from "@next/mdx";

const withMDX = nextMDX({ extension: /\.mdx?$/ });

/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  images: { unoptimized: true },
  output: "export",
  pageExtensions: ["md", "mdx", "ts", "tsx"],
  reactStrictMode: true,
  staticPageGenerationTimeout: 120,
  transpilePackages: ["@databiosphere/findable-ui"],
};

export default withMDX(nextConfig);
