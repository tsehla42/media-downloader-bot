#!/usr/bin/env bash
set -euo pipefail

PROJECT=media-downloader-bot

elapsed() {
  awk "BEGIN {printf \"%.1fs\", $1 / 1000000000}"
}

SCRIPT_START=$(date +%s%N)

docker compose build --no-cache

COMPOSE_PROJECT_NAME=$PROJECT docker compose up -d

SCRIPT_END=$(date +%s%N)
ELAPSED=$((SCRIPT_END - SCRIPT_START))
echo "=== Total: $(elapsed $ELAPSED) ==="
