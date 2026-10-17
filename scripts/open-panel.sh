#!/usr/bin/env bash
#
# Opens the Odin web panel in the browser, waiting for the backend to be ready.
# Used by the desktop autostart entry (~/.config/autostart/odin-panel.desktop)
# and by the Hyprland hook installed by scripts/install-autostart.sh.
#
# Autostart gives this script no terminal, so it never exits silently: every
# failure prints an explicit reason to stderr AND appends it to the panel log
# ($XDG_STATE_HOME/odin/panel.log by default). Override the wait with
# ODIN_PANEL_TIMEOUT (seconds, default 60) and the browser with ODIN_BROWSER.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/odin"
LOG_FILE="$STATE_DIR/panel.log"
PID_FILE="$STATE_DIR/server.pid"
SERVER_LOG="$STATE_DIR/server.log"

mkdir -p "$STATE_DIR"

# Log a line to stderr (visible when run by hand) and to the panel log (the
# only trace left when Hyprland/XDG starts the script with no terminal).
log() {
    local stamp
    stamp="$(date '+%Y-%m-%d %H:%M:%S')"
    printf '[odin-panel] %s\n' "$*" >&2
    printf '%s [odin-panel] %s\n' "$stamp" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

# Give up with an explicit, actionable reason instead of failing silently.
fail() {
    log "[erro] $*"
    exit 1
}


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

is_running() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null
}

# --- Sanity checks: report an invalid install path / config up front --------
if [[ ! -f "$ROOT_DIR/scripts/server.sh" ]]; then
    fail "caminho inválido: '$ROOT_DIR' não parece ser um clone do Odin (scripts/server.sh ausente)."
fi

HOST="${ODIN_HOST:-$(env_value ODIN_HOST 127.0.0.1)}"
PORT="${ODIN_PORT:-$(env_value ODIN_PORT 8000)}"

# When the backend binds 0.0.0.0 the browser still needs a real address.
if [[ -z "$HOST" || "$HOST" == "0.0.0.0" ]]; then
    HOST="127.0.0.1"
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [[ "$PORT" -lt 1 || "$PORT" -gt 65535 ]]; then
    fail "porta inválida: ODIN_PORT='$PORT' (esperado um número entre 1 e 65535)."
fi

URL="http://$HOST:$PORT"
BROWSER="${ODIN_BROWSER:-firefox}"

if ! command -v "$BROWSER" >/dev/null 2>&1 && [[ ! -x "$BROWSER" ]]; then
    fail "navegador não encontrado: '$BROWSER' (defina ODIN_BROWSER com um caminho válido)."
fi

# Wait (default up to ~60s) for the backend to answer before opening the panel,
# so the browser doesn't hit a "connection refused" page on a slow boot.
TIMEOUT="${ODIN_PANEL_TIMEOUT:-60}"
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT" -lt 1 ]]; then
    fail "timeout inválido: ODIN_PANEL_TIMEOUT='$TIMEOUT' (esperado um inteiro de segundos >= 1)."
fi
ATTEMPTS=$(( TIMEOUT * 2 ))  # poll every 0.5s

ready=0
for _ in $(seq 1 "$ATTEMPTS"); do
    if curl -fsS --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.5
done

if [[ "$ready" -ne 1 ]]; then
    if is_running; then
        fail "timeout: backend em execução (PID $(cat "$PID_FILE")) mas não respondeu em ${TIMEOUT}s em $URL — veja $SERVER_LOG"
    else
        fail "backend indisponível: nada respondendo em $URL e nenhum processo em execução — inicie com '$ROOT_DIR/scripts/odin.sh start' e veja $SERVER_LOG"
    fi
fi

log "backend pronto em $URL; abrindo painel com $BROWSER"
exec "$BROWSER" --new-window "$URL"
