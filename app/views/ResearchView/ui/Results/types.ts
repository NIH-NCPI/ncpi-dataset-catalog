import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../types/response";

export interface Props {
  message: AssistantMessage<Response>;
}
