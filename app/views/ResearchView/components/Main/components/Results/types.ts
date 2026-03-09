import {
  AssistantMessage,
  ChatState,
  PromptMessage,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../../types/response";

export interface Props {
  state: ChatState;
}

export type ResultsView =
  | { message: AssistantMessage<Response>; status: STATUS.COMPLETE }
  | { message?: AssistantMessage<Response>; status: STATUS.NOT_FOUND }
  | { message: PromptMessage; status: STATUS.READY }
  | { status: STATUS.LOADING };

export enum STATUS {
  COMPLETE = "COMPLETE",
  LOADING = "LOADING",
  NOT_FOUND = "NOT_FOUND",
  READY = "READY",
}
