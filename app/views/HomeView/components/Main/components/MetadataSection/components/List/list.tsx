import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { CheckCircleRounded } from "@mui/icons-material";
import {
  ListItem,
  ListItemIcon,
  ListItemText,
  Typography,
} from "@mui/material";
import { JSX } from "react";
import { FEATURES } from "./constants";
import { StyledList } from "./list.styles";

/**
 * Renders the feature highlights checklist.
 * @returns Feature list.
 */
export const List = (): JSX.Element => {
  return (
    <StyledList dense disablePadding>
      {FEATURES.map((feature) => (
        <ListItem key={feature} disableGutters disablePadding>
          <ListItemIcon>
            <CheckCircleRounded />
          </ListItemIcon>
          <ListItemText disableTypography>
            <Typography
              component="div"
              variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400}
            >
              {feature}
            </Typography>
          </ListItemText>
        </ListItem>
      ))}
    </StyledList>
  );
};
