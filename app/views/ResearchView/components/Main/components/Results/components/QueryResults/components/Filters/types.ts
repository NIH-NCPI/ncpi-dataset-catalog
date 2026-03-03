import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../../../../../../types/response";
import { RowData, Table } from "@tanstack/react-table";

export interface Props<T extends RowData> {
  message: AssistantMessage<Response>;
  table: Table<T>;
}
