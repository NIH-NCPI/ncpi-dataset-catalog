import { Fragment, JSX } from "react";
import { Props } from "../../types";
import {
  StyledToolbar,
  StyledStack,
} from "@databiosphere/findable-ui/lib/components/Table/components/TableToolbar2/tableToolbar2.styles";
import { TableDownload } from "@databiosphere/findable-ui/lib/components/Table/components/TableFeatures/TableDownload/tableDownload";
import { Divider } from "@mui/material";
import { RowData } from "@tanstack/react-table";

/**
 * Renders the table toolbar with download functionality.
 * @param props - Component props.
 * @param props.table - Table instance from TanStack Table.
 * @returns Table toolbar component.
 */
export const TableToolbar = <T extends RowData>({
  table,
}: Props<T>): JSX.Element => {
  return (
    <Fragment>
      <StyledToolbar>
        <StyledStack>
          <TableDownload table={table} />
        </StyledStack>
      </StyledToolbar>
      <Divider />
    </Fragment>
  );
};
