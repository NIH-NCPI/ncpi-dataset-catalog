import { HomeView } from "app/views/HomeView/homeView";
import { GetStaticProps } from "next";
import { Fragment, JSX } from "react";

export const getStaticProps: GetStaticProps = () => {
  return { props: { homePage: true } };
};

const Page = (): JSX.Element => {
  return <HomeView />;
};

Page.Main = Fragment;

export default Page;
