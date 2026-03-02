import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../../../../../../types/response";
import { Filters } from "@databiosphere/findable-ui/lib/common/entities";
import { RowData, Table } from "@tanstack/react-table";

/**
 * Retrieves the category key for a given facet from the table columns.
 * @param table - Table instance.
 * @param facet - The facet name to find the corresponding column header.
 * @returns The category key (column header) if found, otherwise returns the original facet name.
 */
function getCategoryKey<T extends RowData>(
  table: Table<T>,
  facet: string
): string {
  const column = table.getColumn(facet);

  if (!column) return facet;

  return String(column.columnDef.header);
}

/**
 * Extracts filters from the assistant message response.
 * @param table - Table instance.
 * @param message - Assistant message containing the response with filters.
 * @returns An array of filters with category keys and values.
 */
export function getFilters<T extends RowData>(
  table: Table<T>,
  message: AssistantMessage<Response>
): Filters {
  return message.response.query.mentions.map((mention) => ({
    categoryKey: getCategoryKey(table, mention.facet),
    value: mention.values,
  }));
}
