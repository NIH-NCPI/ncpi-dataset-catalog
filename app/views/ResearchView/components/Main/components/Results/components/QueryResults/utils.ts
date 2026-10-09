import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { TableOptions } from "@tanstack/react-table";
import { Response } from "../../../../../../types/response";
import { Study } from "../../types/study";
import { Variable } from "../../types/variable";
import {
  HIDDEN_COLUMN_VISIBILITY,
  COLUMNS as STUDY_COLUMNS,
} from "./study/columns";
import type { StudyTableMeta } from "./study/types";
import { COLUMNS as VARIABLE_COLUMNS } from "./variable/columns";

type StudyOptions = Omit<TableOptions<Study>, "getCoreRowModel">;
type VariableOptions = Omit<TableOptions<Variable>, "getCoreRowModel">;

/**
 * Utility function to determine table options based on the response message.
 * If there are studies in the response, it returns options for the study table.
 * Otherwise, it returns options for the variable table.
 * @param message - The assistant message containing the response data.
 * @returns Table options for either studies or variables.
 */
export function getOptions(
  message: AssistantMessage<Response>
): StudyOptions | VariableOptions {
  if (message.response.totalStudies > 0) {
    return {
      columns: STUDY_COLUMNS,
      data: message.response.studies,
      getRowId: (row: Study) => row.dbGapId,
      initialState: { columnVisibility: HIDDEN_COLUMN_VISIBILITY },
      meta: {
        consentLongNames: message.response.consentLongNames ?? {},
      } satisfies StudyTableMeta,
    };
  }
  return {
    columns: VARIABLE_COLUMNS,
    data: message.response.variables,
    getRowId: (row: Variable, index: number) => `${row.variableName}-${index}`,
  };
}
