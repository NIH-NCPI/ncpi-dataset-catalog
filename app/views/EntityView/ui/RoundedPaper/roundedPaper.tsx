import type {
  BaseComponentProps,
  ChildrenProps,
} from "@databiosphere/findable-ui/lib/components/types";
import { forwardRef, JSX } from "react";
import { StyledRoundedPaper } from "./roundedPaper.styles";

/**
 * Renders a rounded paper component.
 * @param props - Props.
 * @param props.children - Children.
 * @param props.className - Class name.
 * @returns Rounded paper component.
 */
export const RoundedPaper = forwardRef<
  HTMLDivElement,
  BaseComponentProps & ChildrenProps
>(function RoundedPaper(
  { children, className }: BaseComponentProps & ChildrenProps,
  ref
): JSX.Element {
  return (
    <StyledRoundedPaper className={className} elevation={0} ref={ref}>
      {children}
    </StyledRoundedPaper>
  );
});
