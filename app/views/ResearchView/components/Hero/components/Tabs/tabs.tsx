import { JSX } from "react";
import { useCount } from "./hooks/UseCount/hook";
import { StyledTabs } from "./tabs.styles";
import { Props } from "./types";
import { Tab } from "@mui/material";
import { RESEARCH_TYPE } from "../../../../artifact/types";

/**
 * Renders research view tabs.
 * @param props - Props.
 * @param props.researchType - Research type.
 * @returns Research view tabs.
 */
export const Tabs = ({ researchType }: Props): JSX.Element => {
  const { count } = useCount();

  return (
    <StyledTabs value={researchType}>
      <Tab
        label={renderTabLabel("Results", count)}
        value={RESEARCH_TYPE.RESULTS}
      />
    </StyledTabs>
  );
};

/**
 * Renders a tab label, with an optional count.
 * @param label - Tab label.
 * @param count - Optional count to display.
 * @returns Tab label, with optional count.
 */
function renderTabLabel(label: string, count?: number): string {
  if (!count) return label;

  return `${label} (${count})`;
}
