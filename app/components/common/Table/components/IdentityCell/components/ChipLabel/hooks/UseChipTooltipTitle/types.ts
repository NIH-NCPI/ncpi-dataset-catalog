import type { RefObject } from "react";

export interface UseChipTooltipTitle {
  ref: RefObject<HTMLSpanElement | null>;
  title: string | null;
}
