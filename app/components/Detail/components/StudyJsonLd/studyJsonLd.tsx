import { JSX } from "react";
import Head from "next/head";
import { NCPICatalogStudy } from "../../../../apis/catalog/ncpi-catalog/common/entities";
import { buildStudyJsonLd } from "../../../../utils/schemaOrg";

interface Props {
  browserURL: string;
  study: NCPICatalogStudy;
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
  return (
    <Head>
      <script
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        type="application/ld+json"
      />
    </Head>
  );
};
