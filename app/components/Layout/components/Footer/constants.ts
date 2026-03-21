import { SELECTOR } from "@databiosphere/findable-ui/lib/common/selectors";
import type { LogoProps } from "@databiosphere/findable-ui/lib/components/Layout/components/Header/components/Content/components/Logo/logo";
import { ANCHOR_TARGET } from "@databiosphere/findable-ui/lib/components/Links/common/entities";
import { LinkProps } from "@databiosphere/findable-ui/lib/components/Links/components/Link/link";
import { AppBarProps } from "@mui/material";

export const APP_BAR_PROPS: AppBarProps = {
  color: "inherit",
  component: "footer",
  id: SELECTOR.FOOTER,
  variant: "footer",
};

export const LINK_PROPS: (Omit<LinkProps, "label"> & { label: string })[] = [
  { label: "Status", url: "/status" },
  {
    label: "Feedback & Support",
    url: "https://github.com/NIH-NCPI/ncpi-dataset-catalog/issues/new?template=feedback.md",
  },
];

export const LOGO_PROPS: LogoProps = {
  alt: "NCPI Dataset Catalog",
  height: 36,
  link: "/",
  src: "/images/logoNCPI.png",
};

export const POWERED_BY_CC_PROPS: LogoProps = {
  alt: "Powered by CleverCanary",
  height: 32,
  link: "https://clevercanary.com/",
  src: "/images/powered-by-clevercanary.webp",
  target: ANCHOR_TARGET.BLANK,
};
