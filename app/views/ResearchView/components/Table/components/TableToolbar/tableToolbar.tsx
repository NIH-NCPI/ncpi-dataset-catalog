import { Fragment, JSX } from "react";
import { Props } from "../../types";
import {
  StyledToolbar,
  StyledStack,
} from "@databiosphere/findable-ui/lib/components/Table/components/TableToolbar2/tableToolbar2.styles";
import { TableDownload } from "@databiosphere/findable-ui/lib/components/Table/components/TableFeatures/TableDownload/tableDownload";
import { Divider } from "@mui/material";

export const TableToolbar = ({ table }: Props): JSX.Element => {
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
