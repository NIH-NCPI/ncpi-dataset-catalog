import NextHead from "next/head";
import { useRouter } from "next/router";
import { JSX } from "react";

const DEFAULT_DESCRIPTION =
  "Search 2,944 studies across AnVIL, BDC, CRDC, and KFDRC.";
const OG_IMAGE_PATH = "/favicons/web-app-manifest-512x512.png";
const TWITTER_SITE = "@clevercanary";

interface OgMetaProps {
  appTitle: string;
  browserURL?: string;
  pageDescription?: string;
  pageTitle?: string;
}

/**
 * Renders Open Graph and Twitter Card meta tags for social link previews.
 * @param props - Component props.
 * @param props.appTitle - Application title used as site name and title fallback.
 * @param props.browserURL - Base URL for canonical links and image.
 * @param props.pageDescription - Page-specific description (falls back to site default).
 * @param props.pageTitle - Page-specific title (combined with appTitle).
 * @returns Head element with OG meta tags.
 */
export const OgMeta = ({
  appTitle,
  browserURL,
  pageDescription,
  pageTitle,
}: OgMetaProps): JSX.Element => {
  const router = useRouter();
  const description = pageDescription || DEFAULT_DESCRIPTION;
  const title = pageTitle ? `${pageTitle} - ${appTitle}` : appTitle;
  const url = browserURL ? `${browserURL}${router.asPath}` : "";
  const imageUrl = browserURL ? `${browserURL}${OG_IMAGE_PATH}` : OG_IMAGE_PATH;

  return (
    <NextHead>
      <meta
        key="og:description"
        property="og:description"
        content={description}
      />
      <meta key="og:image" property="og:image" content={imageUrl} />
      <meta key="og:image:width" property="og:image:width" content="512" />
      <meta key="og:image:height" property="og:image:height" content="512" />
      <meta key="og:site_name" property="og:site_name" content={appTitle} />
      <meta key="og:title" property="og:title" content={title} />
      <meta key="og:type" property="og:type" content="website" />
      {url && <meta key="og:url" property="og:url" content={url} />}
      <meta key="twitter:card" name="twitter:card" content="summary" />
      <meta key="twitter:image" name="twitter:image" content={imageUrl} />
      <meta key="twitter:site" name="twitter:site" content={TWITTER_SITE} />
      <meta
        key="twitter:creator"
        name="twitter:creator"
        content={TWITTER_SITE}
      />
    </NextHead>
  );
};
