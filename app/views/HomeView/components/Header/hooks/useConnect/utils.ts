const DATA_NO_TRANSITION = "data-header-no-transition";

/**
 * Suppresses the header CSS transition for one frame.
 * Prevents a visible flash when the header state changes instantly
 * (e.g. navigating to or from the home page).
 */
export function suppressTransition(): void {
  document.body.setAttribute(DATA_NO_TRANSITION, "");
  requestAnimationFrame(() => {
    document.body.removeAttribute(DATA_NO_TRANSITION);
  });
}
