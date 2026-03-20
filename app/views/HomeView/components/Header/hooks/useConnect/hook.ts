import { RefObject, useEffect } from "react";

const DATA_ATTRIBUTE = "data-header-state";

const INTERSECTION_OPTIONS = { rootMargin: "0px 0px 0px 0px", threshold: 0 };

/**
 * Bridges the header and home view sections via a DOM data attribute.
 * The header (rendered in _app.tsx by the DX library) and the observed
 * section (rendered in homeView.tsx) are in disconnected parts of the
 * component tree with no shared prop or context path. This hook uses an
 * IntersectionObserver to set `data-header-state="solid"` on the body
 * when the observed element scrolls out of view, allowing the header
 * styles to respond via a CSS attribute selector.
 * @param ref - Ref to the element to observe.
 */
export function useConnect(ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (!ref.current) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        document.body.removeAttribute(DATA_ATTRIBUTE);
        return;
      }

      document.body.setAttribute(DATA_ATTRIBUTE, "solid");
    }, INTERSECTION_OPTIONS);

    observer.observe(ref.current);

    return (): void => {
      observer.disconnect();
      document.body.removeAttribute(DATA_ATTRIBUTE);
    };
  }, [ref]);
}
