import { getPayload } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Form/utils";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { useQuery } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/hooks/UseQuery/hook";
import Router from "next/router";
import { JSX } from "react";
import { ExampleQuery } from "../../constants";
import { ROUTES } from "../../../../../routes/constants";
import { StyledChip, StyledForm } from "./queryChip.styles";

/**
 * Renders a clickable chip that submits a query and navigates to the research page.
 * @param props - Component props.
 * @param props.label - Display label for the chip.
 * @param props.query - Query string to submit.
 * @returns Query chip component.
 */
export const QueryChip = ({ label, query }: ExampleQuery): JSX.Element => {
  const { state } = useChatState();
  const { onSubmit } = useQuery();
  const { status } = state;
  return (
    <StyledForm
      onSubmit={async (e) => {
        await onSubmit(e, getPayload(e), {
          onMutate: () => Router.push(ROUTES.RESEARCH_STUDIES),
          status,
        });
      }}
    >
      <StyledChip
        clickable
        component="button"
        data-query={query}
        label={label}
        type="submit"
        variant="outlined"
      />
    </StyledForm>
  );
};
