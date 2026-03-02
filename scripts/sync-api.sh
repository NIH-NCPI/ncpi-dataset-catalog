#!/usr/bin/env bash
set -euo pipefail

# JSON source root
SRC_ROOT="catalog"

API_DIR="public/api"
mkdir -p "$API_DIR"

PER_APP_JSONS=("ncpi-platform-studies")

rm -f "$API_DIR"/*.json

for name in "${PER_APP_JSONS[@]}"; do
  src="$SRC_ROOT/${name}.json"
  dst="$API_DIR/${name}.json"
  cp "$src" "$dst"
done
