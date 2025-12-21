#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

echo \"Deleting ./out/\"
rm -rf ./out

n 20.10.0
npm ci

# Build
npm run build:prod

export BUCKET=s3://bhy-ncpi-data.org
export SRCDIR=out/

aws s3 sync  $SRCDIR $BUCKET --delete  --profile excira
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile excira