import { JSX } from "react";
import { StyledGrid, StyledRequestAccess } from "./hero.styles";
import { Props } from "./types";
import { Title } from "@databiosphere/findable-ui/lib/components/common/Title/title";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { ICON_BUTTON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/iconButton";
import { IconButton, Stack } from "@mui/material";
import { BackArrowIcon } from "@databiosphere/findable-ui/lib/components/common/CustomIcon/components/BackArrowIcon/backArrowIcon";
import { SVG_ICON_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/svgIcon";
import { ROUTES } from "../../../../../routes/constants";
import Link from "next/link";
import { STACK_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/stack";

/**
 * Renders the hero section of the study detail view, which includes the request access component.
 * @param props - Props.
 * @param props.study - Study to display.
 * @returns Hero component.
 */
export const Hero = ({ study }: Props): JSX.Element => {
  return (
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
        <Title variant={TYPOGRAPHY_PROPS.VARIANT.HEADING_SMALL} sx={{ py: 1 }}>
          {study.title}
        </Title>
      </Stack>
      <StyledRequestAccess ncpiCatalogStudy={study} />
    </StyledGrid>
  );
};
