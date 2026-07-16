#!/usr/bin/env bash
set -euo pipefail

# JSON source root
SRC_ROOT="catalog"

API_DIR="public/api"
mkdir -p "$API_DIR"

# Studies list JSON served at runtime to the /studies list. The canonical
# artifact is slimmed to the list-column fields and minified (see
# scripts/slim-list-artifact.mjs and epic #425 stage 3b). The full record set
# stays available at <name>-full.json so a revert is a code change (point
# apiPath back) rather than a rebuild — keep it for one release, then drop it.
SLIM_JSONS=("ncpi-platform-studies")

rm -f "$API_DIR"/*.json

for name in "${SLIM_JSONS[@]}"; do
  src="$SRC_ROOT/${name}.json"
  node scripts/slim-list-artifact.mjs "$src" "$API_DIR/${name}.json"
  cp "$src" "$API_DIR/${name}-full.json"
done
