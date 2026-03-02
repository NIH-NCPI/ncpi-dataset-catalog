import { JSX } from "react";
import { Props } from "./types";
import { Table } from "./components/Table/table";
import { useTable } from "./hooks/UseTable/hook";
import { getOptions } from "./utils";
import { RowData, TableOptions } from "@tanstack/table-core";
import { Filters } from "./components/Filters/filters";
import { StyledStack } from "./queryResults.styles";
import { Typography } from "@mui/material";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";

/**
 * Component to render the results of a research query, displaying either studies or variables in a table format.
 * @param props - Component props.
 * @param props.message - The assistant message containing the response data.
 * @returns The rendered results component.
 */
export const QueryResults = ({ message }: Props): JSX.Element => {
  const { table } = useTable(getOptions(message) as TableOptions<RowData>);
  return (
    <StyledStack gap={4} useFlexGap>
      <Typography variant={TYPOGRAPHY_PROPS.VARIANT.HEADING_SMALL}>
        {message.response.totalStudies > 0 ? "Datasets" : "Variables"}
      </Typography>
      <Filters message={message} table={table} />
      <Table table={table} />
    </StyledStack>
  );
};
