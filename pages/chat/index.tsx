import { Main } from "@databiosphere/findable-ui/lib/components/Layout/components/ContentLayout/components/Main/main";
import { GetStaticProps } from "next";
import { JSX } from "react";
import { Chat } from "../../app/components/Chat/chat";

export const getStaticProps: GetStaticProps = async () => {
  return {
    props: {
      pageTitle: "Chat",
    },
  };
};

const Page = (): JSX.Element => {
  return <Chat />;
};

Page.Main = Main;

export default Page;
