import { JSX } from "react";
import { Props } from "./types";
import { Table } from "../../components/Table/table";
import { useTable } from "./hooks/UseTable/hook";
import { getOptions } from "./utils";
import { RowData, TableOptions } from "@tanstack/table-core";

/**
 * Component to render the results of a research query, displaying either studies or variables in a table format.
 * @param props - Component props.
 * @param props.message - The assistant message containing the response data.
 * @returns The rendered results component.
 */
export const Results = ({ message }: Props): JSX.Element => {
  const { table } = useTable(getOptions(message) as TableOptions<RowData>);
  return <Table table={table} />;
};
