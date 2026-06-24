#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Media Downloader Bot Update ==="

echo "Pulling latest changes..."
git pull

bash "$SCRIPT_DIR/refresh-ig-cookies.sh"

echo "Rebuilding and restarting bot..."
bash "$SCRIPT_DIR/compose.sh"

echo "=== Update complete ==="
