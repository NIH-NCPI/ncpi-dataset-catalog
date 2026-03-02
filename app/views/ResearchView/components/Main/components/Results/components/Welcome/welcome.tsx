import { JSX } from "react";
import { StyledStack } from "./welcome.styles";
import { Props } from "./types";
import { Typography, Stack } from "@mui/material";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Chips } from "@databiosphere/findable-ui/lib/views/ResearchView/assistant/components/Messages/components/PromptMessage/components/Chips/chips";

/**
 * Renders the welcome message, with pre-configured query chips.
 * @param props - Component props.
 * @param props.message - Message.
 * @returns Welcome component.
 */
export const Welcome = ({ message }: Props): JSX.Element => {
  return (
    <StyledStack gap={6} useFlexGap>
      <Stack gap={2} useFlexGap>
        <Typography
          component="h1"
          variant={TYPOGRAPHY_PROPS.VARIANT.HEADING_SMALL}
        >
          Start with your research question
        </Typography>
        <Typography
          color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
          variant={TYPOGRAPHY_PROPS.VARIANT.BODY_400}
        >
          Describe what you&apos;re studying — I&apos;ll build a research plan
          and find matching datasets across 2,944 studies from AnVIL, BDC, CRDC,
          and KFDRC.
        </Typography>
      </Stack>
      <Chips message={message} />
    </StyledStack>
  );
};
