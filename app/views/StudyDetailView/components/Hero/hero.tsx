import { JSX } from "react";
import { StyledGrid } from "./hero.styles";
import { Props } from "./types";
import { RequestAccess } from "../../../../components/RequestAccess/requestAccess";
import { Title } from "@databiosphere/findable-ui/lib/components/common/Title/title";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { ICON_BUTTON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/iconButton";
import { IconButton } from "@mui/material";
import { BackArrowIcon } from "@databiosphere/findable-ui/lib/components/common/CustomIcon/components/BackArrowIcon/backArrowIcon";
import { SVG_ICON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/svgIcon";
import { ROUTES } from "../../../../../routes/constants";
import Link from "next/link";

/**
 * Renders the hero section of the study detail view, which includes the request access component.
 * @param props - Props.
 * @param props.study - Study to display.
 * @returns Hero component.
 */
export const Hero = ({ study }: Props): JSX.Element => {
  return (
    <StyledGrid>
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
      <Title variant={TYPOGRAPHY_PROPS.VARIANT.HEADING_SMALL}>
        {study.title}
      </Title>
      <RequestAccess ncpiCatalogStudy={study} />
    </StyledGrid>
  );
};
