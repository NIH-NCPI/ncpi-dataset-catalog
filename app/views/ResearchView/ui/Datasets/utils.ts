import {
  AssistantMessage,
  ChatState,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../ResearchView/types/response";
import { STATUS, DatasetsView } from "./types";
import {
  isInitialPromptMessage,
  isAssistantMessage,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";

/**
 * Determines the current datasets view based on messages and status.
 * @param state - Chat state.
 * @returns The view state with typed message when applicable.
 */
export function getDatasetsView(state: ChatState): DatasetsView {
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
  }

  return { status: STATUS.NOT_FOUND };
}
