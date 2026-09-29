#!/usr/bin/env bash
set -euo pipefail

PROJECT=media-downloader-bot

elapsed() {
  awk "BEGIN {printf \"%.1fs\", $1 / 1000000000}"
}

SCRIPT_START=$(date +%s%N)

# Pre-create bind-mount sources as the invoking user BEFORE `docker compose up`.
# Docker auto-creates missing sources as root, which blocks appuser (uid 1000)
# from writing cookie uploads. Paths are resolved from this script's location
# because compose.sh may run with cwd=scripts/shell.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "${REPO_ROOT}/cookies"
for f in ig-cookies.txt tiktok-cookies.txt yt-cookies.txt; do
  [ -e "${REPO_ROOT}/${f}" ] || : > "${REPO_ROOT}/${f}"
done
if [ ! -w "${REPO_ROOT}/cookies" ]; then
  echo "WARNING: ${REPO_ROOT}/cookies is not writable by $(id -un)."
  echo "  Cookie uploads will fail. Fix with:"
  echo "  sudo chown -R $(id -u):$(id -g) ${REPO_ROOT}/cookies"
fi

docker compose build --no-cache

COMPOSE_PROJECT_NAME=$PROJECT docker compose up -d

SCRIPT_END=$(date +%s%N)
ELAPSED=$((SCRIPT_END - SCRIPT_START))
echo "=== Total: $(elapsed $ELAPSED) ==="
