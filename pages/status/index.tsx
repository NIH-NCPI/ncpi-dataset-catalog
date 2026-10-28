import { GetStaticProps } from "next";
import { JSX } from "react";
import { Status } from "../../app/components/Status/status";

export const getStaticProps: GetStaticProps = async () => {
  return {
    props: {
      pageTitle: "Status",
    },
  };
};

const Page = (): JSX.Element => {
  return <Status />;
};

export default Page;
