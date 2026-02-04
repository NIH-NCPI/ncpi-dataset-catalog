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

aws s3 sync  $SRCDIR $BUCKET --delete  --profile ncpi-prod-deployer
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile ncpi-prod-deployer