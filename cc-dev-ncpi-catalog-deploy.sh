#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

# Run from the repo root regardless of invocation directory — everything below
# (env scrub, .nvmrc, npm ci, out/) assumes it.
cd "$(cd "$(dirname "$0")" && pwd)"

# Preflight: ensure s5cmd is available
if ! command -v s5cmd >/dev/null 2>&1; then
  echo "Error: s5cmd is not installed. Install with: brew install peak/tap/s5cmd" >&2
  exit 1
fi

# Preflight: ensure n is available (used to pin the Node version)
if ! command -v n >/dev/null 2>&1; then
  echo "Error: n is not installed. Install with: brew install n" >&2
  exit 1
fi

# Scrub local env overrides so they can't ship in the build (#403; see README).
rm -fv .env.local .env.*.local

echo "Deleting ./out/"
rm -rf ./out

# Node version comes from .nvmrc — deploys (here) and CI (node-version-file)
# both read it; package.json engines mirrors it (#403). tr strips whitespace,
# incl. a stray CR on CRLF checkouts, which would break n.
n "$(tr -d '[:space:]' < .nvmrc)"
npm ci

# Build
npm run build:dev

export BUCKET=s3://g78-ncpi-data.humancellatlas.dev/
export SRCDIR=out/

AWS_PROFILE=excira s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id EJ5E27A5IGM2B --paths "/*" --profile excira
