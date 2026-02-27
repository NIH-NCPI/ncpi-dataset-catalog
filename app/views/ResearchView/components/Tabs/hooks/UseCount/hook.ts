import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { useMemo } from "react";
import { Response } from "../../../../types/response";
import { isAssistantMessage } from "@databiosphere/findable-ui/lib/common/ai/guards/guards";

/**
 * Returns the count of studies or variables from the latest assistant message response.
 * @returns - Count.
 */
export const useCount = (): { count: number } => {
  const { state } = useChatState();

  const message = useMemo(
    () => state.messages[state.messages.length - 1],
    [state.messages]
  );

  if (isAssistantMessage<Response>(message)) {
    const { response } = message;
    const { totalStudies, totalVariables } = response || {};

    return { count: totalVariables || totalStudies };
  }

  return { count: 0 };
};
