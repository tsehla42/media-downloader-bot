#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_DIR="${SCRIPT_DIR}/scripts/shell"

show_menu() {
    cat <<EOF
Media Downloader Bot — Script Menu

  1) deploy         Fetch + reset, then run update script
  2) update         Git pull, refresh cookies, run compose script
  3) compose        Build image and restart container
  4) dev            Run local dev container
  5) dev-stop       Stop dev container, remove image, cleanup
  6) refresh-ig     Check and refresh Instagram cookies
  7) pull-logs      Pull logs from production server
  8) version        Show local and production server versions

Usage:
  ./bot.sh          Show this menu
  ./bot.sh <num>    Run script by number
  ./bot.sh <name>   Run script by name (e.g. ./bot.sh compose)
  ./bot.sh -v       Show version info

EOF
}

run_compose()  { bash "${SHELL_DIR}/compose.sh" "$@"; }
run_deploy()   { bash "${SHELL_DIR}/deploy.sh" "$@"; }
run_update()   { bash "${SHELL_DIR}/update.sh" "$@"; }
run_dev()      { clear && bash "${SHELL_DIR}/compose.sh" "$@" && docker logs media-downloader-bot -f; }
run_dev_stop() { bash "${SHELL_DIR}/dev-stop.sh" "$@"; }
run_refresh()  { bash "${SHELL_DIR}/refresh-ig-cookies.sh" "$@"; }
run_pull()     { bash "${SHELL_DIR}/pull-logs.sh" "$@"; }
run_version()  { bash "${SHELL_DIR}/version.sh" "$@"; }

# No args -> show menu
if [[ $# -eq 0 ]]; then
    show_menu
    read -rp "Select [1-8]: " choice
    set -- "$choice"
fi

case "${1}" in
    -v|version)     run_version "${@:2}" ;;
    1|deploy)       run_deploy "${@:2}" ;;
    2|update)       run_update "${@:2}" ;;
    3|compose)      run_compose "${@:2}" ;;
    4|dev)          run_dev "${@:2}" ;;
    5|dev-stop)     run_dev_stop "${@:2}" ;;
    6|refresh-ig)   run_refresh "${@:2}" ;;
    7|pull-logs)    run_pull "${@:2}" ;;
    8|version)      run_version "${@:2}" ;;
    *)
        echo "Unknown command: ${1}"
        echo "Run './bot.sh' for usage."
        exit 1
        ;;
esac
