#!/usr/bin/env bash
# Remove the login watcher. Does not delete Messages, and does not uninstall imsg
# unless you leave it for Homebrew yourself.
# --remove-state also deletes the state folder (inbox, pipeline, audit).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY=0
REMOVE_STATE=0

usage() {
  cat <<'EOF'
Usage: bash uninstall.sh [--apply] [--remove-state]

With no flags, prints what would be removed and changes nothing.
--apply removes the login watcher only.
--remove-state also deletes the state folder. Your Messages history is not in that folder.
imsg itself is left installed.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --remove-state) REMOVE_STATE=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ICC_HOME="${ICC_HOME:-$HOME/.imessage-command-center}"
LABEL="com.easybutton.imessage-command-center"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

echo "Would remove the watcher plist if it exists: ${PLIST}"
if [[ "$REMOVE_STATE" -eq 1 ]]; then
  echo "Would delete the state folder: ${ICC_HOME}"
else
  echo "State folder would be kept: ${ICC_HOME}"
fi
echo "Would not uninstall imsg, and would not touch Messages."

if [[ "$APPLY" -eq 0 ]]; then
  echo "Dry run only. Re-run with --apply after you approve this plan."
  exit 0
fi

if [[ -z "$ICC_HOME" || "$ICC_HOME" == "/" || "$ICC_HOME" == "$HOME" || "$ICC_HOME" == "$ROOT" ]]; then
  echo "Refusing to delete that folder." >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  DOMAIN="gui/$(id -u)"
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Watcher removed."
else
  echo "Not macOS, so there is no login watcher to remove."
fi

if [[ "$REMOVE_STATE" -eq 1 ]]; then
  rm -rf "$ICC_HOME"
  echo "State folder deleted."
fi
