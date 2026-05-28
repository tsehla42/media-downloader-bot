#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "No .venv found. Creating one..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python src/bot.py "$@"
