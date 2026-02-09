# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/claude-code) when working with code in this repository.

## Project Overview

This is the **NCPI Dataset Catalog**, a Next.js-based web application that catalogs biomedical research datasets from multiple NIH data repositories (AnVIL, BDC, CRDC, KFDRC). Built with TypeScript, React 18, and Material-UI.

## Common Commands

### Development

```bash
npm run dev          # Start development server
npm run build:dev    # Build for development
npm run build:prod   # Build for production
```

### Testing & Linting

```bash
npm run test         # Run Jest tests (watch mode)
npm run test:e2e     # Run Playwright E2E tests
npm run lint         # Run ESLint
npm run check-format # Check Prettier formatting
```

### Catalog Data Management

```bash
npm run build-ncpi-db           # Build the complete catalog database
npm run update-all-ncpi-sources # Update data from all platforms
npm run update-anvil-source     # Update AnVIL data
npm run update-bdc-source       # Update BDC data
npm run update-crdc-source      # Update CRDC data
npm run update-kfdrc-source     # Update KFDRC data
npm run update-dbgap-source     # Update dbGaP data
npm run fetch-dbgap-selected-publications # Fetch PI-curated publications from dbGaP GapExchange XML
```

### Updating Publications

To refresh publication data displayed on study detail pages:

1. `npm run fetch-dbgap-selected-publications` — Fetches PI-curated PMIDs from each study's GapExchange XML on the dbGaP FTP server, then resolves full metadata (title, authors, DOI, journal, citation count) via Semantic Scholar. Outputs `catalog/dbgap-selected-publications.json` (not checked into git).
2. `npm run build-ncpi-db` — Rebuilds the catalog, merging publications into `catalog/ncpi-platform-studies.json`.

The fetch step takes ~30 minutes (rate-limited FTP + S2 API calls for ~3,000 studies).

## Architecture

- **`app/`** - Next.js application source (components, APIs, config, utilities)
- **`catalog/`** - Generated catalog data (JSON files)
- **`catalog-build/`** - Build scripts and source CSVs for catalog generation
- **`scripts/`** - Shell scripts for deployment and setup

## Code Style

- **TypeScript** with strict configuration
- **ESLint** with SonarJS, JSDoc requirements, and TypeScript-sort-keys
- **Prettier** for formatting
- **Conventional commits** enforced via commitlint (e.g., `feat:`, `fix:`, `chore:`)

## Key Patterns

- Static site generation via Next.js `output: "export"`
- Material-UI components with Emotion CSS-in-JS
- MDX support for markdown content with React components
- Data sourced from CSV files in `catalog-build/source/`

## Node Version

Requires Node.js 22.12.0
