#!/bin/sh
set -eu

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
exec "$VENV_DIR/bin/python" collector.py "$@"
