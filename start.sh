#!/usr/bin/env bash
# تشغيل البوت بخطوة واحدة على لينكس أو ماك:  bash start.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo "  Goose Goose Duck  -  Roles Bot  (Arabic Guide)"
echo "============================================================"

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "[X] Python 3 is not installed."; exit 1; }

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/4] Creating the virtual environment..."
  "$PYTHON" -m venv .venv
fi

echo "[2/4] Installing libraries..."
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt

echo "[3/4] Checking your settings and the token..."
./.venv/bin/python check_setup.py

echo "[4/4] Starting the bot... (press Ctrl+C to stop)"
exec ./.venv/bin/python -u bot.py
