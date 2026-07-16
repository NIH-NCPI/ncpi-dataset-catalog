import { Stack } from "@mui/material";
import { JSX } from "react";
import {
  buildStudyApplyingForAccess,
  buildStudyDescription,
} from "../../../../../../viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";
import { STUDY_DETAIL_SUBPATH } from "../../../../constants";
import { Access } from "./components/Access/access";
import { Description } from "./components/Description/description";
import { Props } from "./types";

/**
 * Renders the overview section of the study detail view.
 * @param props - Props.
 * @param props.study - Study.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Overview section of the study detail view.
 */
export const Overview = ({ study, subpath }: Props): JSX.Element | null => {
  if (subpath !== STUDY_DETAIL_SUBPATH.OVERVIEW) return null;
  return (
    <Stack gap={4} useFlexGap>
      <Description {...buildStudyDescription(study)} />
      <Access {...buildStudyApplyingForAccess()} />
    </Stack>
  );
};
