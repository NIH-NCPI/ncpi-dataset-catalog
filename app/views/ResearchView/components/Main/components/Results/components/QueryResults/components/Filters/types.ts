import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { RowData, Table } from "@tanstack/react-table";
import { Response } from "../../../../../../../../types/response";

export interface Props<T extends RowData> {
  message: AssistantMessage<Response>;
  table: Table<T>;
}
