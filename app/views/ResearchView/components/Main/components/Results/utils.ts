import {
  AssistantMessage,
  ChatState,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../../types/response";
import { STATUS, ResultsView } from "./types";
import {
  isInitialPromptMessage,
  isAssistantMessage,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";

/**
 * Determines the current results view based on messages and status.
 * @param state - Chat state.
 * @returns The view state with typed message when applicable.
 */
export function getResultsView(state: ChatState): ResultsView {
  const { messages, status } = state;

  if (status.loading) return { status: STATUS.LOADING };

  // Get the last message to determine the view state.
  const message = messages[messages.length - 1];

  if (isInitialPromptMessage(message)) {
    return { message, status: STATUS.READY };
  }

  if (isAssistantMessage(message)) {
    const assistantMessage = message as AssistantMessage<Response>;
    const { response } = assistantMessage;
    if (response.totalStudies > 0 || response.totalVariables > 0) {
      return {
        message: assistantMessage,
        status: STATUS.COMPLETE,
      };
    }
    return { message: assistantMessage, status: STATUS.NOT_FOUND };
  }

  return { status: STATUS.NOT_FOUND };
}
