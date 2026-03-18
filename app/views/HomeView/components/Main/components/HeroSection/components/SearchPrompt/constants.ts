import { PromptMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";

/**
 * Prompt message for the search prompt component.
 * Only the `suggestions` field is used here; the type assertion to `PromptMessage`
 * satisfies the `StyledChips` prop contract while omitting fields (e.g. `text`, `type`)
 * that are irrelevant outside the chat context.
 */
export const PROMPT_MESSAGE = {
  suggestions: [
    {
      label: "Diabetes studies with whole genome sequencing",
      query: "Diabetes studies with whole genome sequencing",
    },
    {
      label: "Pediatric cancer on KFDRC",
      query: "Pediatric cancer on KFDRC",
    },
    {
      label: "All variables measuring chocolate consumption",
      query: "All variables measuring chocolate consumption",
    },
  ],
} as PromptMessage;
