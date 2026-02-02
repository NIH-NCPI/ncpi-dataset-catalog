import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { Attribute } from "../../../../../../viewModelBuilders/dataDictionaryMapper/types";
import { Chip, Typography, Grid } from "@mui/material";
import { StyledGrid } from "./fieldCell.styles";
import { buildRequired, buildRange } from "./utils";
import { CodeCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/CodeCell/codeCell";
import { getPartialCellContext } from "../utils";
import { MarkdownCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/MarkdownCell/markdownCell";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { COLUMN_IDENTIFIERS } from "../../../../../../viewModelBuilders/dataDictionaryMapper/columnIds";
import { RankedCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/RankedCell/rankedCell";
import { GRID_PROPS } from "./constants";

export const FieldCell = ({
  row,
  table,
}: CellContext<Attribute, unknown>): JSX.Element => {
  return (
    <StyledGrid>
      <Typography component="div" variant={TYPOGRAPHY_PROPS.VARIANT.BODY_500}>
        <RankedCell
          {...getPartialCellContext(
            row.original.title,
            COLUMN_IDENTIFIERS.TITLE
          )}
          row={row}
          table={table}
        />
      </Typography>
      <Grid {...GRID_PROPS}>
        <CodeCell
          {...getPartialCellContext(
            <MarkdownCell
              {...getPartialCellContext(
                row.original.name,
                COLUMN_IDENTIFIERS.NAME
              )}
              row={row}
              table={table}
            />
          )}
        />
      </Grid>
      {row.original.required && <Chip {...buildRequired(row.original)} />}
      <div>{buildRange(row.original)}</div>
    </StyledGrid>
  );
};
