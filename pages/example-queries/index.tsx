import { Main } from "@databiosphere/findable-ui/lib/components/Layout/components/ContentLayout/components/Main/main";
import { GetStaticProps } from "next";
import { JSX } from "react";
import { ExampleQueriesView } from "../../app/views/ExampleQueriesView/exampleQueriesView";

export const getStaticProps: GetStaticProps = async () => {
  return { props: { pageTitle: "Example Queries" } };
};

/**
 * Example queries page.
 * @returns Example queries page component.
 */
const Page = (): JSX.Element => {
  return <ExampleQueriesView />;
};

Page.Main = Main;

export default Page;
