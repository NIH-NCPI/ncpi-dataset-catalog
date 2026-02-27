import {
  AssistantMessage,
  PromptMessage,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "app/views/ResearchView/types/response";

export type DatasetsView =
  | { message: AssistantMessage<Response>; status: STATUS.COMPLETE }
  | { message: PromptMessage; status: STATUS.READY }
  | { status: STATUS.LOADING }
  | { status: STATUS.NOT_FOUND };

export enum STATUS {
  COMPLETE = "COMPLETE",
  LOADING = "LOADING",
  NOT_FOUND = "NOT_FOUND",
  READY = "READY",
}
