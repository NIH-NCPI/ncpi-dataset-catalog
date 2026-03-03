import { Fragment, JSX } from "react";
import {
  StyledGrid,
  StyledRequestAccess,
  StyledTabs,
  StyledTitle,
} from "./hero.styles";
import { Props } from "./types";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { ICON_BUTTON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/iconButton";
import { IconButton, Stack, Tab } from "@mui/material";
import { BackArrowIcon } from "@databiosphere/findable-ui/lib/components/common/CustomIcon/components/BackArrowIcon/backArrowIcon";
import { SVG_ICON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/svgIcon";
import { ROUTES } from "../../../../../routes/constants";
import Link from "next/link";
import { STACK_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/stack";
import Router from "next/router";

/**
 * Renders the hero section of the study detail view, which includes the request access component.
 * @param props - Props.
 * @param props.researchType - Research type for the study detail view ("results").
 * @param props.study - Study to display.
 * @param props.studyId - Study ID.
 * @param props.subpath - Subpath for the study detail view.
 * @returns Hero component.
 */
export const Hero = ({
  researchType,
  study,
  studyId,
  subpath,
}: Props): JSX.Element => {
  return (
    <Fragment>
      <StyledGrid>
        <Stack
          alignItems={STACK_PROPS.ALIGN_ITEMS.FLEX_START}
          direction={STACK_PROPS.DIRECTION.ROW}
          gap={4}
          useFlexGap
        >
          <IconButton
            color={ICON_BUTTON_PROPS.COLOR.SECONDARY}
            component={Link}
            href={ROUTES.RESEARCH_DATASETS}
          >
            <BackArrowIcon
              color={SVG_ICON_PROPS.COLOR.INK_LIGHT}
              fontSize={SVG_ICON_PROPS.FONT_SIZE.SMALL}
            />
          </IconButton>
          <StyledTitle variant={TYPOGRAPHY_PROPS.VARIANT.HEADING_SMALL}>
            {study.title}
          </StyledTitle>
        </Stack>
        <StyledRequestAccess ncpiCatalogStudy={study} />
      </StyledGrid>
      <StyledTabs
        onChange={(_, v) =>
          Router.push({ query: { researchType, studyParams: [studyId, v] } })
        }
        value={subpath}
      >
        <Tab label="Overview" value="" />
        <Tab label="Selected Publications" value="selected-publications" />
      </StyledTabs>
    </Fragment>
  );
};
