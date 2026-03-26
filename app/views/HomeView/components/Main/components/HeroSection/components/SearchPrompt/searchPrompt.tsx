import { CHIP_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/chip";
import { getPayload } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Form/utils";
import { Input } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Input/input";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { useQuery } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/hooks/UseQuery/hook";
import Link from "next/link";
import Router from "next/router";
import { JSX } from "react";
import { ROUTES } from "../../../../../../../../../routes/constants";
import { PROMPT_MESSAGE } from "./constants";
import {
  StyledChip,
  StyledChips,
  StyledForm,
  StyledStack,
} from "./searchPrompt.styles";

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
      <Input placeholder="Search for studies or variables" />
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
