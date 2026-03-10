import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../../../../../../../types/response";
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
 * Retrieves the facet name for a given category key (column header) from the table columns.
 * @param table - Table instance.
 * @param categoryKey - The category key (column header) to reverse-lookup.
 * @returns The facet (column id) if found, otherwise returns the original category key.
 */
export function getFacet<T extends RowData>(
  table: Table<T>,
  categoryKey: string
): string {
  const column = table
    .getAllColumns()
    .find((c) => String(c.columnDef.header) === categoryKey);

  if (!column) return categoryKey;

  return column.id;
}

/**
 * A filter entry that also carries the original facet id.
 */
export interface FilterWithFacet {
  categoryKey: string;
  facet: string;
  value: (number | string)[];
}

/**
 * Extracts filters from the assistant message response.
 * Filters out mentions with empty values to avoid rendering chipless filter labels.
 * @param table - Table instance.
 * @param message - Assistant message containing the response with filters.
 * @returns An array of filters with category keys, facet ids, and values.
 */
export function getFilters<T extends RowData>(
  table: Table<T>,
  message: AssistantMessage<Response>
): FilterWithFacet[] {
  return message.response.query.mentions
    .filter(
      (mention) => Array.isArray(mention.values) && mention.values.length > 0
    )
    .map((mention) => ({
      categoryKey: getCategoryKey(table, mention.facet),
      facet: mention.facet,
      value: mention.values,
    }));
}
