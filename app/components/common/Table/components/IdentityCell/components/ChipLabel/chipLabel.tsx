import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { Typography } from "@mui/material";
import { Fragment, JSX } from "react";
import type { Props } from "./types";

/**
 * Renders an identity chip label as "label: value", with the field name in
 * light ink and the value in main ink.
 * @param props - Component props.
 * @param props.label - Field name.
 * @param props.value - Field value.
 * @returns Chip label element.
 */
export const ChipLabel = ({ label, value }: Props): JSX.Element => {
  return (
    <Fragment>
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
    </Fragment>
  );
};
