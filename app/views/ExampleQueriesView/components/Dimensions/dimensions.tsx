import { getPayload } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Form/utils";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { useQuery } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/hooks/UseQuery/hook";
import Router from "next/router";
import { JSX } from "react";
import { ROUTES } from "../../../../../routes/constants";
import { DimensionSection } from "./components/DimensionSection/dimensionSection";
import { DIMENSIONS } from "./constants";
import { StyledForm } from "./dimensions.styles";

/**
 * Renders all search dimensions with a single form wrapping the page.
 * @returns Dimensions component.
 */
export const Dimensions = (): JSX.Element => {
  const { state } = useChatState();
  const { onSubmit } = useQuery();
  const { status } = state;
  return (
    <StyledForm
      onSubmit={async (e: React.FormEvent<HTMLFormElement>) => {
        await onSubmit(e, getPayload(e), {
          onMutate: () => Router.push(ROUTES.RESEARCH_STUDIES),
          status,
        });
      }}
    >
      {DIMENSIONS.map((dimension) => (
        <DimensionSection key={dimension.title} {...dimension} />
      ))}
    </StyledForm>
  );
};
