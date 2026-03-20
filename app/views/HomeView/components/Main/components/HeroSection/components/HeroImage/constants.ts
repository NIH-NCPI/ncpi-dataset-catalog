import { ImageProps } from "next/image";

export const IMAGE_A_PROPS: Omit<ImageProps, "alt"> = {
  height: 323,
  priority: true,
  src: "/home/hero/cloud-a.webp",
  width: 576,
};

export const IMAGE_B_PROPS: Omit<ImageProps, "alt"> = {
  height: 386,
  priority: true,
  src: "/home/hero/cloud-b.webp",
  width: 686,
};
