import { JSX } from "react";
import { useRouter } from "next/router";
import { buildNextQuery, getTabValue } from "./utils";
import { NCPICatalogStudy } from "app/apis/catalog/ncpi-catalog/common/entities";
import { StyledTabs } from "./tabs.styles";

/**
 * Renders tabs for the study detail page, allowing navigation between the "Overview" and "Selected Publications" tabs.
 * The current tab is determined by the query parameters in the URL, and changing tabs updates the URL accordingly.
 * @param props - Component props.
 * @param props.publications - Array of publications associated with the study, used to display the count in the "Selected Publications" tab.
 * @returns Tabs element for the study detail page.
 */
export const Tabs = ({
  publications,
}: NCPICatalogStudy): JSX.Element | null => {
  const { push, query } = useRouter();
  return (
    <StyledTabs
      onTabChange={(v) => push({ query: buildNextQuery(query, v) })}
      tabs={[
        { label: "Overview", value: "" },
        {
          count: String(publications.length),
          label: "Selected Publications",
          value: "selected-publications",
        },
      ]}
      value={getTabValue(query)}
    />
  );
};
