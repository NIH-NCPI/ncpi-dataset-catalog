import { StyledHeader } from "app/views/HomeView/components/Header/header.styles";
import { HomeView } from "app/views/HomeView/homeView";
import { Fragment, JSX } from "react";

const Page = (): JSX.Element => {
  return <HomeView />;
};

Page.Main = Fragment;
Page.Header = StyledHeader;

export default Page;
