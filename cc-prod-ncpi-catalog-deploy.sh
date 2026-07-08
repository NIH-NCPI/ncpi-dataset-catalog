#!/usr/bin/env bash
# Set the script to exit immediately on error
set -e

# Run from the repo root regardless of invocation directory — everything below
# (git worktree, .nvmrc) assumes it.
cd "$(cd "$(dirname "$0")" && pwd)"

# Preflight: confirm this really is the repo root with the Node pin present
# (protects symlinked/copied invocations and checkouts predating .nvmrc).
if [ ! -f package.json ] || [ ! -f .nvmrc ]; then
  echo "Error: $(pwd) is not the repo root (package.json/.nvmrc missing)." >&2
  exit 1
fi

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

# Deploys build committed state only — refuse if tracked files have
# uncommitted changes, so the artifact is exactly what HEAD says (#403).
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Error: uncommitted changes to tracked files. Commit or stash them, then re-run the deploy:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

# Build in a fresh worktree of HEAD, where only tracked files exist — local
# overrides like .env.local (which `next build` loads and inlines) cannot leak
# into the artifact because they are never there in the first place (#403;
# see README "Local backend override").
BUILD_ROOT="$(mktemp -d)"
BUILD_DIR="$BUILD_ROOT/repo"
cleanup() {
  git worktree remove --force "$BUILD_DIR" >/dev/null 2>&1 || rm -rf "$BUILD_DIR"
  git worktree prune
  rmdir "$BUILD_ROOT" 2>/dev/null || true
}
trap cleanup EXIT
git worktree add --detach "$BUILD_DIR" HEAD

# Node version comes from .nvmrc — deploys (here) and CI (node-version-file)
# both read it; package.json engines mirrors it (#403). tr strips whitespace,
# incl. a stray CR on CRLF checkouts, which would break n.
n "$(tr -d '[:space:]' < .nvmrc)"

(cd "$BUILD_DIR" && npm ci && npm run build:prod)

export BUCKET=s3://bhy-ncpi-data.org
export SRCDIR="$BUILD_DIR/out/"

AWS_PROFILE=ncpi-prod-deployer s5cmd sync --delete "$SRCDIR" "$BUCKET"
aws cloudfront create-invalidation --distribution-id ENV5LQ3SY9LXL --paths "/*" --profile ncpi-prod-deployer
