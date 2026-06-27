import { Fragment, JSX } from "react";
import { IMAGE_A_PROPS, IMAGE_B_PROPS } from "./constants";
import { StyledGridItemA, StyledGridItemB } from "./heroImage.styles";

/**
 * Renders the hero background images positioned across two grid areas.
 * @returns Hero image.
 */
export const HeroImage = (): JSX.Element => {
  return (
    <Fragment>
      <StyledGridItemA>
        {/* eslint-disable-next-line @next/next/no-img-element -- static export (output: "export") disables next/image optimization; these are decorative hero images */}
        <img {...IMAGE_A_PROPS} alt="NCPI" />
      </StyledGridItemA>
      <StyledGridItemB>
        {/* eslint-disable-next-line @next/next/no-img-element -- static export (output: "export") disables next/image optimization; these are decorative hero images */}
        <img {...IMAGE_B_PROPS} alt="NCPI" />
      </StyledGridItemB>
    </Fragment>
  );
};
