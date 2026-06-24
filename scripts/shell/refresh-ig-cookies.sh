#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Checking Instagram cookies..."
if python scripts/python/check_cookies.py 2>/dev/null; then
    echo "Cookies are fresh."
else
    echo "Cookies are stale or missing. Refreshing..."
    if python scripts/python/ig_login_local.py; then
        echo "Cookies refreshed successfully."
    else
        echo "WARNING: Cookie refresh failed. Instagram downloads may not work."
        echo "Try running: python scripts/python/ig_login_local.py"
    fi
fi
