#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

echo \"Deleting ./out/\"
rm -rf ./out

n 22.12.0
npm ci

# Build
npm run build:dev

export BUCKET=s3://g78-ncpi-data.humancellatlas.dev/
export SRCDIR=out/

# Export AWS credentials for s5cmd (doesn't support --profile)
eval "$(aws configure export-credentials --profile excira --format env)"

s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id EJ5E27A5IGM2B --paths "/*" --profile excira
