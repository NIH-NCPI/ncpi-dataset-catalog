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
BUILD_ROOT="$(mktemp -d)"
BUILD_DIR="$BUILD_ROOT/repo"
trap 'git worktree remove --force "$BUILD_DIR" >/dev/null 2>&1 || true; rm -rf "$BUILD_ROOT"; git worktree prune >/dev/null 2>&1 || true' EXIT
git worktree add --detach "$BUILD_DIR" HEAD

# Node pin comes from .nvmrc; package.json engines and CI mirror it (#403).
n "$(tr -d '[:space:]' < .nvmrc)"
(cd "$BUILD_DIR" && npm ci && npm run build:dev)

AWS_PROFILE=excira s5cmd sync --delete "$BUILD_DIR/out/" s3://g78-ncpi-data.humancellatlas.dev/
aws cloudfront create-invalidation --distribution-id EJ5E27A5IGM2B --paths "/*" --profile excira
