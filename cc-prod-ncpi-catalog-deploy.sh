#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

echo \"Deleting ./out/\"
rm -rf ./out

n 22.12.0
npm ci

# Build
npm run build:prod

export BUCKET=s3://bhy-ncpi-data.org
export SRCDIR=out/

# Export AWS credentials for s5cmd (doesn't support --profile)
eval "$(aws configure export-credentials --profile ncpi-prod-deployer --format env)"

s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile ncpi-prod-deployer
