# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NCPI Dataset Catalog is a Next.js static site that aggregates and displays biomedical research datasets from four NIH cloud platforms: AnVIL, BDC (BioData Catalyst), CRDC (Cancer Research Data Commons), and KFDRC (Kids First Data Resource Center). Built on top of the `@databiosphere/findable-ui` library.

## Common Commands

```bash
# Development
npm run dev                       # Start dev server (builds catalog data first)
npm run lint                      # Run ESLint
npm run check-format              # Check Prettier formatting

# Testing
npm run test                      # Run Jest in watch mode
npm run test:e2e                  # Run Playwright e2e tests (requires server on localhost:3000)

# Building
npm run build:dev                 # Build for development environment
npm run build:prod                # Build for production (static export to out/)

# Catalog Data Pipeline
npm run build-ncpi-db             # Rebuild catalog from source TSV files
npm run update-all-ncpi-sources   # Fetch latest data from all 4 platforms
npm run update-anvil-source       # Fetch AnVIL data only
npm run update-bdc-source         # Fetch BDC data only
npm run update-crdc-source        # Fetch CRDC data only
npm run update-kfdrc-source       # Fetch KFDRC data only
```

## Architecture

### Data Build Pipeline

```
Platform APIs (AnVIL, BDC, CRDC, KFDRC)
    ↓  update-*-source.ts scripts
catalog-build/source/dashboard-source-ncpi.tsv  (dbGapId → platform mapping)
    ↓  build-ncpi-catalog.ts
catalog/ncpi-platform-studies.json  (individual studies with platforms[])
catalog/ncpi-platforms.json         (aggregated platform statistics)
```

Studies can exist on multiple platforms. The build process groups by dbGapId and tracks which platforms host each study.

### Key Directories

- `app/` - Core application code (APIs, components, config, viewModelBuilders)
- `catalog-build/` - Data pipeline scripts (excluded from TypeScript compilation)
- `catalog/` - Generated JSON data files (built at deploy time)
- `site-config/ncpi-catalog/{dev,prod}/` - Environment-specific configuration
- `pages/` - Next.js pages with dynamic routing for entities

### Configuration System

Requires Node.js 22.12.0

### Configuration System

Site configuration lives in `site-config/ncpi-catalog/`:

- `dev/config.ts` - Main configuration with entity definitions, category filters, layout
- `prod/config.ts` - Extends dev config, overrides URLs and analytics
- Build scripts copy `.env` and favicons from site-config to project root

Config is loaded via `NEXT_PUBLIC_SITE_CONFIG` environment variable.

### Entity Configuration Pattern

Entities (Studies, Platforms) are defined in `site-config/.../index/` with:

- `list.columns[]` - Table column definitions with viewBuilder functions
- `detail.tabs[].mainColumn/sideColumn/top` - Detail page layout
- `entityMapper` - Data transformation at load time
- `exploreMode: CS_FETCH_CS_FILTERING` - All data pre-loaded, client-side filtering

### View Model Builders

Located in `app/viewModelBuilders/`. Pure functions that transform entity data into component props:

```typescript
buildPlatforms(entity) → NTagCell props
buildConsentCodes(entity) → ConsentCodesCell props
buildStudyHero(entity) → BackPageHero props
```

These are referenced in EntityConfig to wire data to UI components.

### findable-ui Integration

The `@databiosphere/findable-ui` library provides:

- Core providers (DXConfigProvider, ExploreStateProvider, etc.)
- Layout components (AppLayout, Header, Footer)
- Table/list rendering infrastructure
- Client-side search and filtering

Webpack aliases in `next.config.mjs` ensure peer dependencies resolve correctly.

## Code Style Requirements

ESLint enforces:

- **Sorted keys**: Object keys, interface properties, and enums must be alphabetically sorted
- **Sorted destructure keys**: Destructured properties must be sorted
- **Explicit return types**: Required on all functions (except `.styles.ts` files)
- **JSDoc requirements**: Functions need descriptions, @param, and @returns documentation

## Static Generation

The site uses `output: "export"` for static HTML generation. Catalog data is JSON files loaded at build time - no runtime API calls for catalog content. All filtering/search happens client-side on pre-loaded data.
