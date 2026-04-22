import { ROW_DIRECTION } from "@databiosphere/findable-ui/lib/components/Table/common/entities";
import { TableBody } from "@databiosphere/findable-ui/lib/components/Table/components/TableBody/tableBody";
import { TableHead } from "@databiosphere/findable-ui/lib/components/Table/components/TableHead/tableHead";
import { useVirtualization } from "@databiosphere/findable-ui/lib/components/Table/hooks/UseVirtualization/hook";
import { GridTable } from "@databiosphere/findable-ui/lib/components/Table/table.styles";
import { getColumnTrackSizing } from "@databiosphere/findable-ui/lib/components/TableCreator/options/columnTrackSizing/utils";
import { TableContainer } from "@mui/material";
import { RowData } from "@tanstack/react-table";
import { JSX } from "react";
import { TableToolbar } from "./components/TableToolbar/tableToolbar";
import { StyledRoundedPaper } from "./table.styles";
import { Props } from "./types";

/**
 * Renders a data table with toolbar, header, and virtualized body.
 * @param props - Component props.
 * @param props.table - Table instance from TanStack Table.
 * @returns Table component.
 */
export const Table = <T extends RowData>({ table }: Props<T>): JSX.Element => {
  const { rows, scrollElementRef, virtualizer } = useVirtualization({
    rowDirection: ROW_DIRECTION.DEFAULT,
    table,
  });
  return (
    <StyledRoundedPaper elevation={0}>
      <TableToolbar table={table} />
      <TableContainer ref={scrollElementRef}>
        <GridTable
          gridTemplateColumns={getColumnTrackSizing(
            table.getVisibleFlatColumns()
          )}
          stickyHeader
        >
          <TableHead tableInstance={table} />
          <TableBody
            rowDirection={ROW_DIRECTION.DEFAULT}
            rows={rows}
            tableInstance={table}
            virtualizer={virtualizer}
          />
        </GridTable>
      </TableContainer>
    </StyledRoundedPaper>
  );
};
