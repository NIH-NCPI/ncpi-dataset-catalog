import { JSX } from "react";
import { getResultsView } from "./utils";
import { STATUS } from "./types";
import { Welcome } from "./components/Welcome/welcome";
import { Props } from "./types";
import { StyledLoadingIcon, StyledRoundedPaper } from "./results.styles";
import { SVG_ICON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/svgIcon";
import { QueryResults } from "./components/QueryResults/queryResults";
import { Typography } from "@mui/material";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";

/**
 * Selects the appropriate results view based on chat state.
 * @param props - Component props.
 * @param props.state - Chat state.
 * @returns The selected view component.
 */
export const Results = ({ state }: Pick<Props, "state">): JSX.Element => {
  const view = getResultsView(state);

  switch (view.status) {
    case STATUS.LOADING:
      return <StyledLoadingIcon fontSize={SVG_ICON_PROPS.FONT_SIZE.MEDIUM} />;
    case STATUS.READY:
      return <Welcome message={view.message} />;
    case STATUS.COMPLETE:
      return <QueryResults message={view.message} />;
    case STATUS.NOT_FOUND:
      return (
        <StyledRoundedPaper elevation={0}>
          <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}>
            No results found.
          </Typography>
        </StyledRoundedPaper>
      );
  }
};
