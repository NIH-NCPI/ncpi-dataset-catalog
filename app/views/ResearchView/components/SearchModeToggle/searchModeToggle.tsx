import { ToggleButton, ToggleButtonGroup } from "@mui/material";
import { useRouter } from "next/router";
import { JSX, MouseEvent } from "react";

type SearchMode = "agent" | "pipeline";

const ENV_DEFAULT: SearchMode =
  process.env.NEXT_PUBLIC_SEARCH_MODE === "agent" ? "agent" : "pipeline";

/**
 * Dev toggle that switches the natural-language search backend between the
 * deterministic pipeline (`/search`) and the agentic loop (`/search/agent`),
 * via the `?searchMode=` query param (read by the search form at submit time).
 * @returns The search-mode toggle.
 */
export const SearchModeToggle = (): JSX.Element => {
  const router = useRouter();
  const param = router.query.searchMode;
  const mode: SearchMode =
    param === "agent" || param === "pipeline" ? param : ENV_DEFAULT;

  /**
   * Update the `?searchMode` query param when the user flips the toggle.
   * @param _event - The toggle click event (unused).
   * @param value - The selected mode, or null when the active button is re-clicked.
   */
  const handleChange = (
    _event: MouseEvent<HTMLElement>,
    value: SearchMode | null
  ): void => {
    if (!value) return;
    router.push({ query: { ...router.query, searchMode: value } }, undefined, {
      shallow: true,
    });
  };

  return (
    <ToggleButtonGroup
      color="primary"
      exclusive
      onChange={handleChange}
      size="small"
      value={mode}
    >
      <ToggleButton value="pipeline">Pipeline</ToggleButton>
      <ToggleButton value="agent">Agent (spike)</ToggleButton>
    </ToggleButtonGroup>
  );
};
