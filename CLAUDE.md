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
```

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
