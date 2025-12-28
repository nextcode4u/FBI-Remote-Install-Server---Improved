#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
TARGET="$1"
[ -z "$TARGET" ] && TARGET="."
command -v python3 >/dev/null 2>&1 && PY=python3
command -v python >/dev/null 2>&1 && [ -z "$PY" ] && PY=python
if [ -z "$PY" ]; then
  echo "Python not installed:"
  echo "https://www.python.org/downloads/"
  exit 1
fi
echo "FBI Remote Installer Enhanced"
$PY "$SCRIPT_DIR/servefiles.py" "$TARGET"
