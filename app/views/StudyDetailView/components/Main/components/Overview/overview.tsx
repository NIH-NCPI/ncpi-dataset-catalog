import { JSX } from "react";
import { Props } from "./types";
import {
  buildStudyApplyingForAccess,
  buildStudyDescription,
} from "../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import { Description } from "./components/Description/description";
import { Access } from "./components/Access/access";
import { Stack } from "@mui/material";

/**
 * Renders the overview section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Overview section of the study detail view.
 */
export const Overview = ({ study, subpath }: Props): JSX.Element | null => {
  if (subpath !== "") return null;
  return (
    <Stack gap={4} useFlexGap>
      <Description {...buildStudyDescription(study)} />
      <Access {...buildStudyApplyingForAccess()} />
    </Stack>
  );
};
