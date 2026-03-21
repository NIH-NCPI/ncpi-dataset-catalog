import { VersionInfo } from "@databiosphere/findable-ui/lib/components/Layout/components/Footer/components/VersionInfo/versionInfo";
import {
  AppBar,
  Link,
  Links,
} from "@databiosphere/findable-ui/lib/components/Layout/components/Footer/footer.styles";
import { Logo } from "@databiosphere/findable-ui/lib/components/Layout/components/Header/components/Content/components/Logo/logo";
import { useLayoutDimensions } from "@databiosphere/findable-ui/lib/providers/layoutDimensions/hook";
import { Toolbar } from "@mui/material";
import { JSX } from "react";
import {
  APP_BAR_PROPS,
  LINK_PROPS,
  LOGO_PROPS,
  POWERED_BY_CC_PROPS,
} from "./constants";

/**
 * Renders the footer.
 * @returns Footer.
 */
export const Footer = (): JSX.Element => {
  const { footerRef } = useLayoutDimensions();
  return (
    <AppBar {...APP_BAR_PROPS} ref={footerRef}>
      <Toolbar variant="dense">
        <Logo {...LOGO_PROPS} />
        <Links>
          {LINK_PROPS.map((linkProps) => (
            <Link key={linkProps.label} {...linkProps} />
          ))}
          <VersionInfo />
          <Logo {...POWERED_BY_CC_PROPS} />
        </Links>
      </Toolbar>
    </AppBar>
  );
};
