import { JSX } from "react";
import { DimensionsSection } from "./components/Main/components/DimensionsSection/dimensionsSection";
import { HeroSection } from "./components/Main/components/HeroSection/heroSection";
import { MetadataSection } from "./components/Main/components/MetadataSection/metadataSection";
import { PlatformsSection } from "./components/Main/components/PlatformsSection/platformsSection";

/**
 * Renders the home view.
 * @returns Home view.
 */
export const HomeView = (): JSX.Element => {
  return (
    <main>
      <HeroSection />
      <DimensionsSection />
      <MetadataSection />
      <PlatformsSection />
    </main>
  );
};
