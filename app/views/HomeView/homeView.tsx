import { JSX, useRef } from "react";
import { useConnect } from "./components/Header/hooks/useConnect/hook";
import { DataAccessSection } from "./components/Main/components/DataAccessSection/dataAccessSection";
import { DimensionsSection } from "./components/Main/components/DimensionsSection/dimensionsSection";
import { HeroSection } from "./components/Main/components/HeroSection/heroSection";
import { MetadataSection } from "./components/Main/components/MetadataSection/metadataSection";
import { PlatformsSection } from "./components/Main/components/PlatformsSection/platformsSection";
import { StyledSkyline } from "./components/Main/components/Section/section.styles";

/**
 * Renders the home view.
 * @returns Home view.
 */
export const HomeView = (): JSX.Element => {
  const observerRef = useRef<HTMLDivElement>(null);
  useConnect(observerRef);
  return (
    <main>
      <StyledSkyline>
        <HeroSection ref={observerRef} />
        <DimensionsSection />
      </StyledSkyline>
      <MetadataSection />
      <PlatformsSection />
      <DataAccessSection />
    </main>
  );
};
