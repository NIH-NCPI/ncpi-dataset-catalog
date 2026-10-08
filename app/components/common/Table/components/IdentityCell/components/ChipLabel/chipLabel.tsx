import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Tooltip, Typography } from "@mui/material";
import { JSX } from "react";
import { useChipTooltipTitle } from "./hooks/UseChipTooltipTitle/hook";
import type { Props } from "./types";

/**
 * Renders an identity chip label as "label: value", with the field name in
 * light ink and the value in main ink. When the chip truncates the label, the
 * value shows in a tooltip, and the label takes focus so keyboard users can
 * open it too.
 * @param props - Component props.
 * @param props.label - Field name.
 * @param props.value - Field value.
 * @returns Chip label element.
 */
export const ChipLabel = ({ label, value }: Props): JSX.Element => {
  const { ref, title } = useChipTooltipTitle(value);
  return (
    <Tooltip arrow describeChild title={title}>
      <span ref={ref} tabIndex={title ? 0 : undefined}>
        <Typography
          color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
          component="span"
          variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400}
        >
          {label}:
        </Typography>{" "}
        <Typography color={TYPOGRAPHY_PROPS.COLOR.INK_MAIN} component="span">
          {value}
        </Typography>
      </span>
    </Tooltip>
  );
};
