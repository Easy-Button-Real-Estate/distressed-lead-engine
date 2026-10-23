#!/usr/bin/env bash
# Install the iMessage Command Center on a Mac.
# No flags: print the plan and change nothing.
# --apply: install the imsg bridge only if it is missing, then create the state folder.
# --launchd: also install a per-user watcher that queues texts and sends nothing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY=0
LAUNCHD=0

usage() {
  cat <<'EOF'
Usage: bash install.sh [--apply] [--launchd]

With no flags, this prints the plan and changes nothing.
--apply installs imsg when the `imsg` command is missing, and creates the state folder.
--launchd also installs a login watcher. The watcher only queues your command chat. It never sends.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --launchd) LAUNCHD=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ICC_HOME="${ICC_HOME:-$HOME/.imessage-command-center}"

cat <<EOF
iMessage Command Center installer
This script does not disable SIP, does not grant permissions for you,
does not read your messages, and does not send any texts.
Bridge: imsg (https://github.com/openclaw/imsg), MIT License, copyright Peter Steinberger.
Install command, only when imsg is missing and you passed --apply:
  brew install steipete/tap/imsg
State folder: ${ICC_HOME}
Project: ${ROOT}
EOF

if [[ "$APPLY" -eq 0 ]]; then
  echo "Dry run only. Re-run with --apply after you approve this plan."
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Refusing to change anything: imsg only runs on macOS." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is missing. Install the Xcode Command Line Tools, then run this again." >&2
  exit 1
fi

if ! command -v imsg >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is missing, so imsg was not installed. Install Homebrew from https://brew.sh and run this again." >&2
    exit 1
  fi
  brew install steipete/tap/imsg
else
  echo "imsg is already on PATH. Leaving that install as it is."
fi

mkdir -p "$ICC_HOME"
chmod 700 "$ICC_HOME"

export ICC_ROOT="$ROOT"
export ICC_HOME
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["ICC_HOME"])
path = home / "config.json"
current = {}
if path.exists():
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        current = loaded
current.setdefault("bridge", "imsg")
current["root"] = os.environ["ICC_ROOT"]
current.setdefault("chat_id", None)
path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY

echo "State folder is ready."
echo "Next clicks, which this script cannot do for you:"
echo "  System Settings → Privacy & Security → Full Disk Access"
echo "  Add Terminal.app and the imsg program (run: which imsg), turn both on, then quit and reopen Terminal."
echo "  The first send asks for Automation permission to control Messages. Allow it."
echo "Then run: python3 -m icc doctor"

if [[ "$LAUNCHD" -eq 0 ]]; then
  exit 0
fi

if ! python3 - <<'PY'
import json, os, sys
from pathlib import Path
data = json.loads((Path(os.environ["ICC_HOME"]) / "config.json").read_text(encoding="utf-8"))
chat_id = data.get("chat_id")
sys.exit(0 if isinstance(chat_id, int) and chat_id > 0 else 1)
PY
then
  echo "imsg is installed, but the watcher was not. Pick the command chat first:" >&2
  echo "  python3 -m icc use-chat --id <id from python3 -m icc chats>" >&2
  echo "Then run: bash install.sh --apply --launchd" >&2
  exit 1
fi

PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"
LABEL="com.easybutton.imessage-command-center"
AGENTS="${HOME}/Library/LaunchAgents"
PLIST="${AGENTS}/${LABEL}.plist"
mkdir -p "$AGENTS"
sed \
  -e "s|__PYTHON__|${PYTHON_BIN}|g" \
  -e "s|__ROOT__|${ROOT}|g" \
  -e "s|__ICC_HOME__|${ICC_HOME}|g" \
  "${ROOT}/launchd/com.easybutton.imessage-command-center.plist.template" \
  > "$PLIST"
chmod 644 "$PLIST"

DOMAIN="gui/$(id -u)"
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
echo "Watcher installed. It queues the command chat only. It does not send texts."
