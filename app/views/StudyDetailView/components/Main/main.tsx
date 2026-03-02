import { JSX } from "react";
import { Props } from "./types";
import {
  buildStudyApplyingForAccess,
  buildStudyDescription,
} from "../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import { Description } from "./components/Description/description";
import { Access } from "./components/Access/access";
import { Stack } from "@mui/material";

/**
 * Renders the main section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @returns Main section of the study detail view.
 */
export const Main = ({ study }: Props): JSX.Element => {
  return (
    <Stack gap={4} useFlexGap>
      <Description {...buildStudyDescription(study)} />
      <Access {...buildStudyApplyingForAccess()} />
    </Stack>
  );
};
