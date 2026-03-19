import { JSX } from "react";
import { DimensionsSection } from "./components/Main/components/DimensionsSection/dimensionsSection";
import { HeroSection } from "./components/Main/components/HeroSection/heroSection";

/**
 * Renders the home view.
 * @returns Home view.
 */
export const HomeView = (): JSX.Element => {
  return (
    <main>
      <HeroSection />
      <DimensionsSection />
    </main>
  );
};
