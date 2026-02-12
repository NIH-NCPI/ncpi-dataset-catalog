import { JSX } from "react";
import Head from "next/head";
import { NCPICatalogStudy } from "../../../../apis/catalog/ncpi-catalog/common/entities";
import { buildStudyJsonLd } from "../../../../utils/schemaOrg";

interface Props {
  browserURL: string;
  study: NCPICatalogStudy;
}

/**
 * Escapes a JSON string for safe embedding in an HTML script tag.
 * Prevents script injection by replacing characters that could break out of the script context.
 * @param json - The JSON string to escape.
 * @returns Escaped JSON string safe for use in dangerouslySetInnerHTML.
 */
function escapeJsonForHtml(json: string): string {
  return json
    .replace(/</g, "\\u003c") // Less-than sign - prevents </script> breakout
    .replace(/>/g, "\\u003e") // Greater-than sign - prevents tag injection
    .replace(/&/g, "\\u0026"); // Ampersand - prevents HTML entity injection
}

/**
 * Renders a Schema.org Dataset JSON-LD script tag in the document head.
 * @param props - Component props.
 * @param props.browserURL - The base URL of the site.
 * @param props.study - The NCPI catalog study.
 * @returns Head element with JSON-LD script tag.
 */
export const StudyJsonLd = ({ browserURL, study }: Props): JSX.Element => {
  const jsonLd = buildStudyJsonLd(study, browserURL);
  const jsonLdString = escapeJsonForHtml(JSON.stringify(jsonLd));
  return (
    <Head>
      <script
        dangerouslySetInnerHTML={{ __html: jsonLdString }}
        type="application/ld+json"
      />
    </Head>
  );
};
