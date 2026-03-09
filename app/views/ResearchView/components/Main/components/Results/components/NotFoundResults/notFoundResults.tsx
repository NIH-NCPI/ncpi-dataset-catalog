import { JSX } from "react";
import { Stack, Typography } from "@mui/material";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { RowData, TableOptions } from "@tanstack/table-core";
import { Response } from "../../../../../../types/response";
import { Filters } from "../QueryResults/components/Filters/filters";
import { useTable } from "../QueryResults/hooks/UseTable/hook";
import { getOptions } from "../QueryResults/utils";

interface Props {
  message: AssistantMessage<Response>;
}

/**
 * Renders a "no results" view with filter chips so users can adjust filters.
 * @param props - Component props.
 * @param props.message - The assistant message containing the response data.
 * @returns Not-found results component with removable filter chips.
 */
export const NotFoundResults = ({ message }: Props): JSX.Element => {
  const { table } = useTable(getOptions(message) as TableOptions<RowData>);
  return (
    <Stack gap={4} useFlexGap>
      <Filters message={message} table={table} />
      <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}>
        No results found.
      </Typography>
    </Stack>
  );
};
