#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

# Run from the repo root regardless of invocation directory — everything below
# (env scrub, .nvmrc, npm ci, out/) assumes it.
cd "$(dirname "$0")"

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

# Scrub local env overrides — `next build` loads .env.local / .env.*.local, so a
# developer's local override (e.g. a localhost API URL) would silently ship in
# the deployed artifact (#403). The -f guard also skips an unmatched glob.
for f in .env.local .env.*.local; do
  if [ -f "$f" ]; then
    echo "Removing local env override $f so it can't leak into the build"
    rm -f "$f"
  fi
done

echo "Deleting ./out/"
rm -rf ./out

# Node version comes from .nvmrc — the single pin, kept in sync with
# package.json engines and CI (#403). tr strips whitespace, incl. a stray CR
# on CRLF checkouts, which would break n.
n "$(tr -d '[:space:]' < .nvmrc)"
npm ci

# Build
npm run build:prod

export BUCKET=s3://bhy-ncpi-data.org
export SRCDIR=out/

AWS_PROFILE=ncpi-prod-deployer s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile ncpi-prod-deployer
