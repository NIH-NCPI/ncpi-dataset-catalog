#!/usr/bin/env bash
set -e
cd "$(cd "$(dirname "$0")" && pwd)"

# Deploys ship HEAD exactly — refuse to run with uncommitted tracked changes.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Error: uncommitted changes to tracked files. Commit or stash them, then re-run." >&2
  exit 1
fi

# Build in a fresh worktree of HEAD so untracked local files (.env.local etc.)
# can't leak into the artifact (#403).
BUILD_DIR="$(mktemp -d)/repo"
trap 'git worktree remove --force "$BUILD_DIR" 2>/dev/null || true; git worktree prune' EXIT
git worktree add --detach "$BUILD_DIR" HEAD

# Node pin comes from .nvmrc; package.json engines and CI mirror it (#403).
n "$(tr -d '[:space:]' < .nvmrc)"
(cd "$BUILD_DIR" && npm ci && npm run build:prod)

AWS_PROFILE=ncpi-prod-deployer s5cmd sync --delete "$BUILD_DIR/out/" s3://bhy-ncpi-data.org
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile ncpi-prod-deployer
