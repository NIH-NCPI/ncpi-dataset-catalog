import { useEffect, useRef, useState } from "react";
import type { UseChipTooltipTitle } from "./types";
import { isLabelOverflowed } from "./utils";

/**
 * Tracks whether the enclosing chip's `.MuiChip-label` is truncated by
 * ellipsis, returning the given title only when it is. Attach the ref to an
 * element rendered inside the chip label. Uses `ResizeObserver` on the label
 * so the result stays accurate across container resizes and font loads; the
 * observer's first callback, which fires on observe, sets the initial value.
 * Re-subscribes when the title changes, since new text in an already-truncated
 * label doesn't resize the element.
 * @param title - Tooltip title to show while the label is truncated.
 * @returns The ref to attach inside the chip label, and the tooltip title
 *   (the given title when truncated, otherwise null).
 */
export const useChipTooltipTitle = (title: string): UseChipTooltipTitle => {
  const ref = useRef<HTMLSpanElement>(null);
  const [isOverflowed, setIsOverflowed] = useState(false);

  useEffect(() => {
    const el = ref.current?.closest<HTMLElement>(".MuiChip-label");
    if (!el) return;
    const observer = new ResizeObserver(() =>
      setIsOverflowed(isLabelOverflowed(el))
    );
    observer.observe(el);
    return (): void => observer.disconnect();
  }, [title]);

  return { ref, title: isOverflowed ? title : null };
};
