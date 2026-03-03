import { JSX } from "react";
import { GetStaticPaths, GetStaticProps } from "next";
import { ResearchView } from "@databiosphere/findable-ui/lib/views/ResearchView/researchView";
import { Artifact } from "../../../app/views/ResearchView/artifact/artifact";
import { ParsedUrlQuery } from "querystring";
import {
  RESEARCH_TYPE,
  ResearchType,
} from "../../../app/views/ResearchView/artifact/types";
import { StyledMain } from "../../../app/views/ResearchView/components/Main/main.styles";

interface Params extends ParsedUrlQuery {
  researchType: ResearchType;
}

interface Props {
  researchType: ResearchType;
}

export const getStaticPaths: GetStaticPaths = async () => {
  return {
    fallback: false,
    paths: [
      { params: { researchType: RESEARCH_TYPE.RESULTS } },
      { params: { researchType: RESEARCH_TYPE.PLAN } },
    ],
  };
};

export const getStaticProps: GetStaticProps<Props, Params> = async ({
  params,
}) => {
  return {
    props: { researchType: params!.researchType },
  };
};

const Page = ({ researchType }: Props): JSX.Element => {
  return (
    <ResearchView>
      <Artifact researchType={researchType} />
    </ResearchView>
  );
};

Page.Main = StyledMain;

export default Page;
