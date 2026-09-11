#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for live-political-analysis.
# Runs after checkout; safe to re-run against a warm snapshot or a cold VM.
set -euo pipefail

cd "$(dirname "$0")/.."

# --- uv (Python toolchain + venv manager, as the README uses) ---
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- System fonts for issue #40's Telegram card rendering ---
# Pillow draws from .ttf files on disk, not font names. telegram_card.py loads
# DejaVu Serif, Serif-Italic and SansMono; on this Ubuntu the italic/mono faces
# live in fonts-dejavu-extra, split out of fonts-dejavu-core. Both are needed or
# the card tests fail with "OSError: cannot open resource".
if [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf ]; then
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends fonts-dejavu-core fonts-dejavu-extra
fi

# --- Python 3.11 venv + package with all local-dev extras (README) ---
# CI pins 3.11; requires-python is >=3.11. sentiment pulls torch/transformers,
# dashboard pulls streamlit/pandas/altair, telegram pulls Pillow, bills pypdf.
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.11 .venv
fi
uv pip install --python .venv/bin/python -e ".[dev,sentiment,dashboard,telegram,bills]"

# --- TypeScript constituency lookup (#77): deps + build public/lookup.js ---
(cd ts && npm ci && npm run build)

echo "install.sh: done"
