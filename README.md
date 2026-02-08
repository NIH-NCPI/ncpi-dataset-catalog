# NCPI Dataset Catalog

A web application that catalogs biomedical research datasets from NIH cloud platforms participating in the [NIH Cloud Platform Interoperability (NCPI)](https://anvilproject.org/ncpi) program: AnVIL, BDC, CRDC, and KFDRC.

Built with Next.js, TypeScript, React, and Material-UI. Uses static site generation to produce a fully exportable site.

## Prerequisites

- Node.js 22.12.0 (see `engines` in package.json)
- npm

## Getting Started

```bash
# Install dependencies
npm install

# Start the development server
npm run dev
```

The site will be available at http://localhost:3000.

## Building the Site

```bash
npm run build:dev    # Development build
npm run build:prod   # Production build
npm run start        # Serve the built site
```

## Catalog Data Pipeline

The site displays study metadata sourced from dbGaP, platform APIs, and other NIH resources. The data pipeline has several stages:

### 1. Update platform sources

Fetches the latest study lists from each cloud platform:

```bash
npm run update-all-ncpi-sources   # Update all platforms
npm run update-anvil-source       # Update AnVIL only
npm run update-bdc-source         # Update BDC only
npm run update-crdc-source        # Update CRDC only
npm run update-kfdrc-source       # Update KFDRC only
npm run update-dbgap-source       # Update dbGaP advanced search CSV
```

### 2. Fetch publications (optional)

Fetches PI-curated publication lists from each study's GapExchange XML on the dbGaP FTP server, then resolves full metadata (title, authors, DOI, journal, citation count) via the Semantic Scholar API.

```bash
npm run fetch-dbgap-publications
```

This produces `catalog/dbgap-publications.json` (~30 MB, not checked into git). The script takes approximately 30 minutes due to rate-limited FTP and API calls across ~3,000 studies.

### 3. Build the catalog database

Merges platform sources, dbGaP metadata, and publications into the final catalog JSON files:

```bash
npm run build-ncpi-db
```

This reads `catalog/dbgap-publications.json` (if present) and attaches publications to each study. The output files (`catalog/ncpi-platform-studies.json` and `catalog/ncpi-platforms.json`) are checked into git and used by the site at build time.

### Full refresh

To completely refresh all data and rebuild:

```bash
npm run update-all-ncpi-sources
npm run fetch-dbgap-publications
npm run build-ncpi-db
npm run build:dev
```

## Testing

```bash
npm run test         # Run Jest unit tests (watch mode)
npm run test:e2e     # Run Playwright end-to-end tests
npm run lint         # Run ESLint
npm run check-format # Check Prettier formatting
```

## Project Structure

```
app/                    Next.js application source
  apis/                 Entity interfaces and data utilities
  components/           React components
  viewModelBuilders/    View model builders for entity detail pages
catalog/                Generated catalog data (JSON)
catalog-build/          Build scripts and source data for catalog generation
  source/               Source CSVs and TSVs from platform APIs
  common/               Shared utilities (dbGaP CSV/FTP, consent codes)
scripts/                Shell scripts for build and deployment
site-config/            Per-environment site configuration
  ncpi-catalog/
    dev/                Development config (entity configs, detail pages)
    prod/               Production overrides
```

## Code Style

- TypeScript with strict configuration
- ESLint with SonarJS, JSDoc requirements, and sorted keys
- Prettier for formatting
- Conventional commits enforced via commitlint (e.g., `feat:`, `fix:`, `chore:`)
