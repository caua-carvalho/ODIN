#!/usr/bin/env bash
#
# Opens the Odin web panel in the browser, waiting for the backend to be ready.
# Used by the desktop autostart entry (~/.config/autostart/odin-panel.desktop).

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"


# Read a KEY=value from the repo .env without sourcing it (values may contain
# spaces). An exported shell variable always wins.
env_value() {
    local key="$1" default="${2:-}" value="" env_file="$ROOT_DIR/.env"

    if [[ -f "$env_file" ]]; then
        value="$(grep -E "^[[:space:]]*${key}=" "$env_file" | tail -n1 | cut -d= -f2-)"
        value="${value%$'\r'}"
        value="${value%\"}"; value="${value#\"}"
        value="${value%\'}"; value="${value#\'}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
    fi

    if [[ -n "$value" ]]; then
        printf '%s' "$value"
    else
        printf '%s' "$default"
    fi
}

HOST="${ODIN_HOST:-$(env_value ODIN_HOST 127.0.0.1)}"
PORT="${ODIN_PORT:-$(env_value ODIN_PORT 8000)}"

# When the backend binds 0.0.0.0 the browser still needs a real address.
if [[ -z "$HOST" || "$HOST" == "0.0.0.0" ]]; then
    HOST="127.0.0.1"
fi

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
