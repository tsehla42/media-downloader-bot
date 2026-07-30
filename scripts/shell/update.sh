#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

elapsed() {
  awk "BEGIN {printf \"%.1fs\", $1 / 1000000000}"
}

echo "=== Media Downloader Bot Update ==="

SCRIPT_START=$(date +%s%N)

echo "Pulling latest changes..."
git pull

bash "$SCRIPT_DIR/refresh-ig-cookies.sh"

echo "Rebuilding and restarting bot..."
bash "$SCRIPT_DIR/compose.sh"

SCRIPT_END=$(date +%s%N)
ELAPSED=$((SCRIPT_END - SCRIPT_START))

echo "=== Update complete ($(elapsed $ELAPSED)) ==="
