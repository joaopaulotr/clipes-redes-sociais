#!/usr/bin/env bash
# macOS/Linux equivalent of iniciar.bat: starts the site + worker and opens the browser.
set -e
cd "$(dirname "$0")"

# Homebrew's default ffmpeg has no libass (needed for the "ass" subtitle filter); prefer ffmpeg-full.
if [ -d /opt/homebrew/opt/ffmpeg-full/bin ]; then
  export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"
fi

[ -f .env ] || cp .env.example .env

PORT="$(grep -E '^PORT=' .env | cut -d= -f2)"
PORT="${PORT:-8000}"
(sleep 3 && open "http://localhost:${PORT}" 2>/dev/null || true) &

uv run python -m clipes
