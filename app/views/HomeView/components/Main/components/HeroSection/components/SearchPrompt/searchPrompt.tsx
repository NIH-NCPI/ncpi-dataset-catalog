import { JSX } from "react";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { getPayload } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Form/utils";
import {
  StyledForm,
  StyledChips,
  StyledStack,
  StyledChip,
} from "./searchPrompt.styles";
import { useQuery } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/hooks/UseQuery/hook";
import { PROMPT_MESSAGE } from "./constants";
import Router from "next/router";
import { ROUTES } from "../../../../../../../../../routes/constants";
import { Input } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Input/input";
import { CHIP_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/chip";
import Link from "next/link";

/**
 * Renders the search prompt component.
 * @returns Search prompt component.
 */
export const SearchPrompt = (): JSX.Element => {
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
      <Input placeholder="Ask anything..." />
      <StyledStack spacing={2} useFlexGap>
        <StyledChips message={PROMPT_MESSAGE} />
        <StyledChip
          component={Link}
          href={ROUTES.STUDIES}
          label="Browse all studies"
          variant={CHIP_PROPS.VARIANT.FILLED}
        />
      </StyledStack>
    </StyledForm>
  );
};
