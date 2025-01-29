import { Breakpoints } from "@mui/system";

export const BREAKPOINTS: Partial<Breakpoints> = {
  values: {
    lg: 1440,
    md: 1280,
    sm: 1024,
    xs: 0,
  } as Breakpoints["values"], // TODO(cc) add "xl" breakpoint.
};

export const GIT_HUB_REPO_URL =
  "https://github.com/NIH-NCPI/ncpi-dataset-catalog";
