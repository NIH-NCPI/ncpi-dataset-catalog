import Document, { Head, Html, Main, NextScript } from "next/document";
import { JSX } from "react";

const SITE_URL = process.env.NEXT_PUBLIC_SITEMAP_DOMAIN || "";
const OG_IMAGE = `${SITE_URL}/favicons/web-app-manifest-512x512.png`;

class MyDocument extends Document {
  render(): JSX.Element {
    return (
      <Html>
        <Head>
          <link
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Roboto+Mono&family=Inter+Tight:ital,wght@0,500;1,500&display=swap"
            rel="stylesheet"
          />
          <meta
            property="og:description"
            content="Search 2,944 studies across AnVIL, BDC, CRDC, and KFDRC."
          />
          <meta property="og:image" content={OG_IMAGE} />
          <meta property="og:site_name" content="NCPI Dataset Catalog" />
          <meta property="og:title" content="NCPI Dataset Catalog" />
          <meta property="og:type" content="website" />
          <meta name="twitter:card" content="summary" />
        </Head>
        <body>
          <Main />
          <NextScript />
        </body>
      </Html>
    );
  }
}

export default MyDocument;
