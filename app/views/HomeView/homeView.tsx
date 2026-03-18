import { JSX } from "react";
import { HeroSection } from "./components/Main/components/HeroSection/heroSection";

/**
 * Renders the home view.
 * @returns Home view.
 */
export const HomeView = (): JSX.Element => {
  return (
    <>
      <HeroSection />
    </>
  );
};
