import { isLabelOverflowed } from "./utils";

/**
 * Builds an element with the given rendered and content widths.
 * @param offsetWidth - Rendered width.
 * @param scrollWidth - Content width.
 * @returns Element.
 */
function buildElement(offsetWidth: number, scrollWidth: number): HTMLElement {
  const el = document.createElement("span");
  Object.defineProperty(el, "offsetWidth", { value: offsetWidth });
  Object.defineProperty(el, "scrollWidth", { value: scrollWidth });
  return el;
}

describe("isLabelOverflowed", () => {
  it("is true when the content is wider than the label", () => {
    expect(isLabelOverflowed(buildElement(100, 140))).toBe(true);
  });

  it("is false when the content fits", () => {
    expect(isLabelOverflowed(buildElement(100, 100))).toBe(false);
  });
});
