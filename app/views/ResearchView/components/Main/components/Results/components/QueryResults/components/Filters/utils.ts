import { SelectedFilter } from "@databiosphere/findable-ui/lib/common/entities";
import {
  AssistantMessage,
  Mention,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Column, RowData, Table } from "@tanstack/react-table";
import { Response } from "../../../../../../../../types/response";
import { CATEGORY_LABEL_OVERRIDES } from "./constants";

/**
 * Retrieves the category label for a given facet from the table columns.
 * @param table - Table instance.
 * @param facet - The facet name to find the corresponding column header.
 * @returns The category label (column header) if found, otherwise returns the original facet name.
 */
function getCategoryLabel<T extends RowData>(
  table: Table<T>,
  facet: string
): string {
  const column = findColumn(table, facet);

  if (!column) return resolveCategoryLabel(facet);

  return String(column.columnDef.header);
}

/**
 * Extracts filters from the assistant message response.
 * Filters out mentions with empty values to avoid rendering chipless filter labels.
 * @param table - Table instance.
 * @param message - Assistant message containing the response with filters.
 * @returns An array of applied filters with category labels for display.
 */
export function getFilters<T extends RowData>(
  table: Table<T>,
  message: AssistantMessage<Response>
): (SelectedFilter & { categoryLabel: string })[] {
  return message.response.query.mentions
    .filter(filterMention)
    .map((mention) => ({
      categoryKey: mention.facet,
      categoryLabel: getCategoryLabel(table, mention.facet),
      value: mention.values,
    }));
}

/**
 * Filters mentions with non-empty values to ensure that only applied filters are displayed.
 * This prevents rendering filter chips without labels when the values array is empty.
 * @param mention - The mention object to check.
 * @returns True if the mention has non-empty values, false otherwise.
 */
function filterMention(mention: Mention): boolean {
  return Array.isArray(mention.values) && mention.values.length > 0;
}

/**
 * Finds a column in the table by its facet name (column id).
 * @param table - Table instance.
 * @param facet - The facet name (column id) to find.
 * @returns The column if found, otherwise undefined.
 */
function findColumn<T extends RowData>(
  table: Table<T>,
  facet: string
): Column<T> | undefined {
  return table.getAllColumns().find((c) => c.id === facet);
}

/**
 * Resolves the display label for a filter category, applying any necessary overrides for specific facets.
 * @param label - Label.
 * @returns Category label (display label) with overrides applied if applicable.
 */
function resolveCategoryLabel(label: string): string {
  return CATEGORY_LABEL_OVERRIDES[label] ?? label;
}
