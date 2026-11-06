#!/bin/bash
# Double-click to start djnext on a Mac. First run installs everything (a few minutes).
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed. A window may pop up offering to install developer tools: accept it, then double-click this file again."
  python3 --version
  read -r -p "Press Enter to close."
  exit 1
fi
if [ ! -x ".venv/bin/djnext" ]; then
  echo "First start: installing djnext (only happens once)..."
  python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -e . -q || {
    echo "Install failed. Send a screenshot of this window to whoever shared djnext with you."
    read -r -p "Press Enter to close."; exit 1; }
fi
.venv/bin/djnext app
