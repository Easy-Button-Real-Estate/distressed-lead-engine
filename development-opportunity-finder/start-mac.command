#!/bin/bash
# Development Opportunity Finder - Mac starter. Double-click it (or run: bash start-mac.command).
#   bash start-mac.command --check         non-interactive preflight: build .venv, install packages, run the setup check, exit
#   bash start-mac.command --which-python  only show which Python it would use, then exit
# What it runs, in order (nothing is sent anywhere except pip downloading the packages in requirements.txt):
#   1) refuses to run from a temporary / translocated copy or from inside a zip
#   2) finds Python 3.10+ (EBRE_PYTHON if you set it, then python3.15 ... python3.10, python.org and Homebrew installs;
#      never Apple's /usr/bin/python3 stub)
#   3) makes a private .venv folder here and installs requirements.txt into it
#   4) runs scripts/doctor.py (setup check, saved to setup_check.txt in this folder)
#   5) checks for Claude Code and starts it in this folder
# If macOS says it can't be opened: System Settings > Privacy & Security, scroll down, click "Open Anyway"
# next to start-mac.command, then confirm. (On recent macOS, Control-click > Open no longer skips this.)
CHECK=0; WHICH=0
[ "$1" = "--check" ] && CHECK=1
[ "$1" = "--which-python" ] && { CHECK=1; WHICH=1; }
pause() { [ "$CHECK" = "1" ] || read -r -p "Press Enter to close." _; }
echo "=================================================================="
echo " Development Opportunity Finder - setup"
echo " You need: Python 3.10 or newer, and Claude Code."
echo " Claude Code needs a PAID Claude plan (Pro, Max, Team or Enterprise)"
echo " or an Anthropic Console account with API billing. The free Claude"
echo " plan does not include Claude Code."
echo "------------------------------------------------------------------"
echo " PRIVACY: The kit's local scripts store and process owner data in"
echo " your kit folder and do not send owner data to public map servers."
echo " However, when Claude Code reads file contents or includes them in"
echo " prompts, that information may be transmitted to Anthropic for"
echo " processing under your Claude plan or API account terms and"
echo " settings. Only use this workflow with data you are authorized to"
echo " share with that service. Keep API keys in the local .env file and"
echo " never paste them into chat."
echo " Permission rules in .claude/settings.json are a safeguard, not a"
echo " guarantee. Details: SECURITY.md"
echo "=================================================================="
# bash builtins only: a no-Python PATH does not include dirname, and bash 5 rejects `cd ""`.
case "$0" in
  */*) _dir=${0%/*} ;;
  *) _dir=. ;;
esac
HERE="$(cd "$_dir" && pwd -P)" || { echo "PROBLEM: can't open this folder."; pause; exit 1; }
cd "$HERE" || { echo "PROBLEM: can't open this folder."; pause; exit 1; }
echo "Folder: $HERE"
case "$HERE" in
  */AppTranslocation/*|/private/var/folders/*|/var/folders/*|*.zip/*|*.zip)
    echo "PROBLEM: this is running from a temporary copy or from inside a zip (macOS opened it straight from the download)."
    echo "FIX: move the whole folder to your home folder, e.g. ~/EBRE-Land, then double-click start-mac.command there."
    pause; exit 1;;
esac
case "$HERE" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
    echo "Note: macOS may ask 'Terminal would like to access files in your Desktop/Documents/Downloads folder'. Click Allow."
    echo "      (Easiest: keep the kit in ~/EBRE-Land, which needs no extra permission.)";;
esac
PY=""
CANDIDATES="python3.15 python3.14 python3.13 python3.12 python3.11 python3.10"
if [ "$EBRE_PATH_ONLY" != "1" ]; then
  for v in 3.15 3.14 3.13 3.12 3.11 3.10; do CANDIDATES="$CANDIDATES /Library/Frameworks/Python.framework/Versions/$v/bin/python3"; done
  CANDIDATES="$CANDIDATES /opt/homebrew/bin/python3 /usr/local/bin/python3"
fi
CANDIDATES="$CANDIDATES python3"
for c in ${EBRE_PYTHON:+"$EBRE_PYTHON"} $CANDIDATES; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  [ -z "$p" ] && continue
  [ "$p" = "/usr/bin/python3" ] && continue   # Apple's stub: may pop up an install dialog and is often too old
  if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' </dev/null 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "PROBLEM: Python 3.10 or newer was not found."
  echo "FIX: install it from https://www.python.org/downloads/ (the macOS installer), then double-click this file again."
  pause; exit 1
fi
echo "Python: $("$PY" --version 2>&1) ($PY)"
[ "$WHICH" = "1" ] && exit 0
FIRST=0
if [ ! -x ".venv/bin/python" ]; then
  FIRST=1
  echo "First run: creating .venv and installing packages (a few minutes on a slow connection)..."
  if ! "$PY" -m venv ".venv"; then
    echo "PROBLEM: could not create .venv. FIX: reinstall Python from python.org, then try again."
    pause; exit 1
  fi
fi
if ! ".venv/bin/python" -m pip install -q --disable-pip-version-check -r requirements.txt </dev/null; then
  echo "PROBLEM: package install failed (no internet, or a firewall). FIX: connect to the internet and double-click again."
  pause; exit 1
fi
if [ "$FIRST" = "1" ] || [ "$CHECK" = "1" ]; then ".venv/bin/python" scripts/doctor.py --online --no-claude-ok; else ".venv/bin/python" scripts/doctor.py --quiet-ok --no-claude-ok; fi
DOC=$?
echo "Setup check saved to: $HERE/setup_check.txt"
if [ "$CHECK" = "1" ]; then echo "Preflight finished (exit $DOC)."; exit $DOC; fi
. ".venv/bin/activate"
if command -v claude >/dev/null 2>&1; then
  echo "Starting Claude Code in this folder. Say: run the demo"
  claude
else
  echo ""
  echo "Packages are ready, but Claude Code is not installed (the 'claude' command)."
  echo "FIX: install it from https://claude.com/claude-code (it needs a paid Claude plan), then double-click this file again."
  echo "Meanwhile you can try the demo without Claude: .venv/bin/python scripts/run_pipeline.py --demo"
  pause
fi
