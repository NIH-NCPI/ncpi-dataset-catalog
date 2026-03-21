import { SocialMedia } from "@databiosphere/findable-ui/lib/components/Layout/components/Header/common/entities";
import * as C from "../../../components/index";

export const SOCIALS = {
  GITHUB: {
    label: "GitHub",
    url: "https://github.com/NIH-NCPI/ncpi-dataset-catalog",
  },
};

export const socialMedia: SocialMedia = {
  socials: [
    {
      ...SOCIALS.GITHUB,
      Icon: C.GitHubIcon,
    },
  ],
};
