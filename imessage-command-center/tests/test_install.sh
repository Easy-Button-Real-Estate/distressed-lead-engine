#!/usr/bin/env bash
# The installer must be safe on a machine that is not the user's Mac.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export ICC_HOME="$TMP/state"
mkdir -p "$HOME"

bash "$ROOT/install.sh" >"$TMP/dry.txt"
grep -q "Dry run only" "$TMP/dry.txt"
grep -q "brew install steipete/tap/imsg" "$TMP/dry.txt"
grep -q "does not disable SIP" "$TMP/dry.txt"
test ! -e "$ICC_HOME"

set +e
bash "$ROOT/install.sh" --apply >"$TMP/apply.txt" 2>"$TMP/apply.err"
code=$?
set -e
test "$code" -eq 1
grep -q "Refusing to change anything" "$TMP/apply.err"
test ! -e "$ICC_HOME"

set +e
bash "$ROOT/install.sh" --nope >"$TMP/bad.txt" 2>"$TMP/bad.err"
code=$?
set -e
test "$code" -eq 2

# The script must not embed the commands that disable protections or install from a pipe.
if grep -Ei 'csrutil|chat-create|curl .*\| *bash|tccutil' "$ROOT/install.sh" "$ROOT/uninstall.sh"; then
  echo "installer contains a forbidden command" >&2
  exit 1
fi

mkdir -p "$ICC_HOME"
echo "keep" >"$ICC_HOME/note.txt"
bash "$ROOT/uninstall.sh" >"$TMP/un-dry.txt"
grep -q "Dry run only" "$TMP/un-dry.txt"
test -f "$ICC_HOME/note.txt"

bash "$ROOT/uninstall.sh" --apply --remove-state >"$TMP/un.txt"
test ! -e "$ICC_HOME"

echo "install tests passed"
