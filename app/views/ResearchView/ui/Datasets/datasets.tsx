import { JSX } from "react";
import { getDatasetsView } from "./utils";
import { STATUS } from "./types";
import { Welcome } from "../Welcome/welcome";
import { Props } from "../../artifact/types";
import { StyledLoadingIcon, StyledRoundedPaper } from "./datasets.styles";
import { SVG_ICON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/svgIcon";
import { Results } from "../Results/results";

/**
 * Selects the appropriate datasets view based on chat state.
 * @param props - Component props.
 * @param props.state - Chat state.
 * @returns The selected view component.
 */
export const Datasets = ({ state }: Pick<Props, "state">): JSX.Element => {
  const datasetsView = getDatasetsView(state);
  const { status } = datasetsView;

  switch (status) {
    case STATUS.LOADING:
      return <StyledLoadingIcon fontSize={SVG_ICON_PROPS.FONT_SIZE.MEDIUM} />;
    case STATUS.READY:
      return <Welcome message={datasetsView.message} />;
    case STATUS.COMPLETE:
      return <Results message={datasetsView.message} />;
    case STATUS.NOT_FOUND:
      return (
        <StyledRoundedPaper elevation={0}>
          No datasets found.
        </StyledRoundedPaper>
      );
  }
};
