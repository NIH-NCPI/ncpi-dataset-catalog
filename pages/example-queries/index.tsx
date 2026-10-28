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

export default Page;
