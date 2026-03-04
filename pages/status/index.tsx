import { Main } from "@databiosphere/findable-ui/lib/components/Layout/components/ContentLayout/components/Main/main";
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

Page.Main = Main;

export default Page;
