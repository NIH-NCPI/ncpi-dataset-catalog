import { Fragment, JSX } from "react";
import { Overview } from "./components/Overview/overview";
import { SelectedPublications } from "./components/SelectedPublications/selectedPublications";
import { Variables } from "./components/Variables/variables";
import { Props } from "./types";

/**
 * Renders the main section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Main section of the study detail view.
 */
export const Main = ({ study, subpath }: Props): JSX.Element => {
  return (
    <Fragment>
      <Overview study={study} subpath={subpath} />
      <SelectedPublications study={study} subpath={subpath} />
      <Variables study={study} subpath={subpath} />
    </Fragment>
  );
};
