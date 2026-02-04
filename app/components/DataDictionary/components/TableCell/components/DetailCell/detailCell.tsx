import { CellContext } from "@tanstack/react-table";
import { JSX } from "react";
import { Attribute } from "../../../../../../viewModelBuilders/dataDictionaryMapper/types";
import { Collapse, Typography } from "@mui/material";
import {
  StyledPaper,
  StyledCell,
  StyledStack,
  StyledCollapse,
  StyledMarkdownCell,
} from "./detailCell.styles";
import { buildExample } from "./utils";
import { getPartialCellContext } from "../utils";
import { TYPOGRAPHY_PROPS } from "./constants";
import { COLUMN_IDENTIFIERS } from "../../../../../../viewModelBuilders/dataDictionaryMapper/columnIds";
import { LinkCell } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/LinkCell/linkCell";

export const DetailCell = ({
  row,
  table,
}: CellContext<Attribute, unknown>): JSX.Element => {
  const { getIsExpanded } = row;
  const isExpanded = getIsExpanded();
  return (
    <StyledCell>
      <Collapse in={isExpanded}>
        <Typography {...TYPOGRAPHY_PROPS}>Description</Typography>
      </Collapse>
      <StyledMarkdownCell
        {...getPartialCellContext(
          row.original.description,
          COLUMN_IDENTIFIERS.DESCRIPTION
        )}
        row={row}
        table={table}
      />
      <StyledCollapse in={isExpanded}>
        {row.original.values && (
          <div>
            <Typography {...TYPOGRAPHY_PROPS}>Allowed Values</Typography>
            <StyledMarkdownCell
              {...getPartialCellContext(
                row.original.values,
                COLUMN_IDENTIFIERS.VALUES
              )}
              row={row}
              table={table}
            />
          </div>
        )}
        {row.original.example && (
          <div>
            <Typography {...TYPOGRAPHY_PROPS}>Example</Typography>
            <StyledStack direction="row">
              {buildExample(row.original).map((example, i) => (
                <StyledPaper key={i} elevation={0}>
                  {example}
                </StyledPaper>
              ))}
            </StyledStack>
          </div>
        )}
        {row.original.rationale && (
          <div>
            <Typography {...TYPOGRAPHY_PROPS}>Rationale</Typography>
            <StyledMarkdownCell
              {...getPartialCellContext(
                row.original.rationale,
                COLUMN_IDENTIFIERS.RATIONALE
              )}
              row={row}
              table={table}
            />
          </div>
        )}
        <div>
          <Typography {...TYPOGRAPHY_PROPS}>Source</Typography>
          <LinkCell {...getPartialCellContext(row.original.source)} />
        </div>
      </StyledCollapse>
    </StyledCell>
  );
};
