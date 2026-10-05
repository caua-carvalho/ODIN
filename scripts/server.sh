#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/odin"
PID_FILE="$STATE_DIR/server.pid"
LOG_FILE="$STATE_DIR/server.log"

HOST="${ODIN_HOST:-127.0.0.1}"
PORT="${ODIN_PORT:-8000}"

mkdir -p "$STATE_DIR"


die() {
    echo "[erro] $1"
    exit 1
}


check_python() {
    if [[ ! -x "$PYTHON" ]]; then
        die "Ambiente Python não encontrado.

Execute:
  $ROOT_DIR/scripts/setup.sh"
    fi
}


is_running() {
    [[ -f "$PID_FILE" ]] || return 1

    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"

    [[ -n "$pid" ]] || return 1

    kill -0 "$pid" 2>/dev/null
}


cleanup_stale_pid() {
    if [[ -f "$PID_FILE" ]] && ! is_running; then
        rm -f "$PID_FILE"
    fi
}


start() {
    check_python
    cleanup_stale_pid

    if is_running; then
        local pid
        pid="$(cat "$PID_FILE")"

        echo "[odin] Backend já está executando."
        echo "       PID:  $pid"
        echo "       URL:  http://$HOST:$PORT"
        return 0
    fi

    echo "[odin] Iniciando backend..."

    cd "$BACKEND_DIR"

    nohup "$PYTHON" -m uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!

    echo "$pid" > "$PID_FILE"

    sleep 1

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "[erro] Backend não iniciou."
        echo
        echo "Últimos logs:"
        tail -n 20 "$LOG_FILE" 2>/dev/null || true
        rm -f "$PID_FILE"
        return 1
    fi

    echo "[ok] Backend iniciado."
    echo "     PID:  $pid"
    echo "     URL:  http://$HOST:$PORT"
    echo "     Log:  $LOG_FILE"
}


stop() {
    cleanup_stale_pid

    if ! is_running; then
        echo "[odin] Backend não está executando."
        return 0
    fi

    local pid
    pid="$(cat "$PID_FILE")"

    echo "[odin] Parando backend (PID $pid)..."

    kill "$pid"

    for _ in {1..20}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "[ok] Backend parado."
            return 0
        fi

        sleep 0.25
    done

    echo "[aviso] Processo não encerrou normalmente."
    echo "[odin] Forçando encerramento..."

    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"

    echo "[ok] Backend parado."
}


restart() {
    stop
    echo
    start
}


status() {
    cleanup_stale_pid

    echo
    echo "ODIN SERVER"
    echo "────────────────────────────────"

    if is_running; then
        local pid
        pid="$(cat "$PID_FILE")"

        echo "Status:    ONLINE"
        echo "PID:       $pid"
        echo "Host:      $HOST"
        echo "Porta:     $PORT"
        echo "URL:       http://$HOST:$PORT"
    else
        echo "Status:    OFFLINE"
        echo "Host:      $HOST"
        echo "Porta:     $PORT"
    fi

    echo "Log:       $LOG_FILE"
    echo
}


logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        echo "[odin] Nenhum log encontrado."
        echo
        echo "O backend ainda não foi iniciado."
        return 0
    fi

    tail -n 100 "$LOG_FILE"
}


logs_follow() {
    if [[ ! -f "$LOG_FILE" ]]; then
        touch "$LOG_FILE"
    fi

    tail -n 100 -f "$LOG_FILE"
}


usage() {
    cat <<EOF
ODIN Server

Uso:
  odin start              Inicia o backend
  odin stop               Para o backend
  odin restart            Reinicia o backend
  odin status             Mostra o status
  odin logs               Mostra os últimos logs
  odin logs --follow      Acompanha os logs em tempo real

Arquivos:
  PID:  $PID_FILE
  LOG:  $LOG_FILE
EOF
}


command="${1:-}"

case "$command" in
    start)
        start
        ;;

    stop)
        stop
        ;;

    restart)
        restart
        ;;

    status)
        status
        ;;

    logs)
        if [[ "${2:-}" == "--follow" || "${2:-}" == "-f" ]]; then
            logs_follow
        else
            logs
        fi
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        usage
        exit 1
        ;;
esac
