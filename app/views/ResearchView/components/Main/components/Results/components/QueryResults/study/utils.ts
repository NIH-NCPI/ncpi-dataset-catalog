import type { Table } from "@tanstack/react-table";
import type { Study } from "../../../types/study";
import type { StudyTableMeta } from "./types";

/**
 * Returns the consent long names, keyed by consent code, from the study table meta.
 * @param table - Study table.
 * @returns Consent long names, or an empty object when the table has no meta.
 */
export function getConsentLongNames(
  table: Table<Study>
): Record<string, string> {
  const meta = table.options.meta as StudyTableMeta | undefined;
  return meta?.consentLongNames ?? {};
}
