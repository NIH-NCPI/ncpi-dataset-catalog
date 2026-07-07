#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

# Preflight: ensure s5cmd is available
if ! command -v s5cmd >/dev/null 2>&1; then
  echo "Error: s5cmd is not installed. Install with: brew install peak/tap/s5cmd" >&2
  exit 1
fi

# Scrub local env overrides — `next build` loads .env.local / .env.*.local, so a
# developer's local override (e.g. a localhost API URL) would silently ship in
# the deployed artifact (#403).
for f in .env.local .env.development.local .env.production.local; do
  if [ -f "$f" ]; then
    echo "Removing local env override $f so it can't leak into the build"
    rm -f "$f"
  fi
done

echo "Deleting ./out/"
rm -rf ./out

# Node version comes from .nvmrc — the single pin, kept in sync with
# package.json engines and CI (#403).
n "$(cat .nvmrc)"
npm ci

# Build
npm run build:dev

export BUCKET=s3://g78-ncpi-data.humancellatlas.dev/
export SRCDIR=out/

AWS_PROFILE=excira s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id EJ5E27A5IGM2B --paths "/*" --profile excira
