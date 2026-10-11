#!/usr/bin/env bash
#
# Opens the Odin web panel in the browser, waiting for the backend to be ready.
# Used by the desktop autostart entry (~/.config/autostart/odin-panel.desktop).

set -uo pipefail

HOST="${ODIN_HOST:-127.0.0.1}"
PORT="${ODIN_PORT:-8000}"
URL="http://$HOST:$PORT"
BROWSER="${ODIN_BROWSER:-firefox}"

# Wait up to ~60s for the backend to answer before opening the panel, so the
# browser doesn't hit a "connection refused" page on a slow boot.
for _ in $(seq 1 120); do
    if curl -fsS --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

exec "$BROWSER" --new-window "$URL"
