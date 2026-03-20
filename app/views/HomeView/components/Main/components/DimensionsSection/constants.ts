import { AccordionProps, SlideProps } from "@mui/material";

export const ACCORDION_PROPS: Omit<AccordionProps, "children"> = {
  slotProps: { transition: { easing: "ease-in-out", timeout: 500 } },
};

export const SLIDE_PROPS: Omit<SlideProps, "children"> = {
  appear: false,
  direction: "left",
  easing: "cubic-bezier(0.22, 0.61, 0.36, 1)",
  exit: false,
  timeout: 800,
};
