import { SocialMedia } from "@databiosphere/findable-ui/lib/components/Layout/components/Header/common/entities";
import * as C from "../../../components/index";

export const SOCIALS = {
  GITHUB: {
    label: "GitHub",
    url: "https://github.com/NIH-NCPI/ncpi-dataset-catalog",
  },
  X: {
    label: "X",
    url: "https://twitter.com/NIHCloudInterop",
  },
  YOUTUBE: {
    label: "YouTube",
    url: "https://www.youtube.com/@ncpi-acc",
  },
};

export const socialMedia: SocialMedia = {
  socials: [
    {
      ...SOCIALS.GITHUB,
      Icon: C.GitHubIcon,
    },
    {
      ...SOCIALS.X,
      Icon: C.XIcon,
    },
    {
      ...SOCIALS.YOUTUBE,
      Icon: C.YouTubeIcon,
    },
  ],
};
