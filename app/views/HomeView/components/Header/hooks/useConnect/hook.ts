import { RefObject, useEffect, useLayoutEffect } from "react";
import { suppressTransition } from "./utils";

const DATA_ATTRIBUTE = "data-header-state";

const INTERSECTION_OPTIONS = { rootMargin: "0px 0px 0px 0px", threshold: 0 };

/**
 * Controls the header's scroll-driven style changes on the home page.
 * The header's initial transparent state is set by the `transparent` prop
 * on StyledHeader (passed from _app.tsx). This hook adds scroll behavior:
 * an IntersectionObserver sets `data-header-state="solid"` on the body
 * when the observed element leaves the viewport, and removes it when
 * it re-enters — allowing the header CSS to transition between states.
 *
 * DOM attributes are used because the header (in _app.tsx) and the
 * observed section (in homeView.tsx) are in disconnected component trees
 * with no shared prop or context path.
 *
 * On mount and dismount, the CSS transition is suppressed for one frame
 * via `data-header-no-transition` to prevent a visible flash during
 * page navigation.
 * @param ref - Ref to the element to observe.
 */
export function useConnect(ref: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    suppressTransition();
  }, []);

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
      suppressTransition();
      document.body.removeAttribute(DATA_ATTRIBUTE);
    };
  }, [ref]);
}
