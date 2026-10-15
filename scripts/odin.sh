#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"
SERVER_SCRIPT="$ROOT_DIR/scripts/server.sh"


usage() {
    cat <<EOF
ODIN

Uso:
  odin                    Abre o chat
  odin start              Inicia o backend
  odin stop               Para o backend
  odin restart            Reinicia o backend
  odin status             Mostra o status do backend
  odin logs               Mostra os logs
  odin logs --follow      Acompanha os logs em tempo real

Comandos:
  start
  stop
  restart
  status
  logs
  help
EOF
}


command="${1:-}"

# When the systemd --user unit is installed, manage the backend through it so
# that Restart=always actually supervises the process and `odin restart` does
# not race the unit. `status`/`logs` keep reading the pidfile/log written by
# server.sh.
use_systemd=0
if command -v systemctl >/dev/null 2>&1 && systemctl --user cat odin.service >/dev/null 2>&1; then
    use_systemd=1
fi


case "$command" in
    start|stop|restart)
        if [[ "$use_systemd" -eq 1 ]]; then
            exec systemctl --user "$command" odin.service
        fi
        exec "$SERVER_SCRIPT" "$@"
        ;;

    status)
        exec "$SERVER_SCRIPT" "$@"
        ;;

    logs)
        exec "$SERVER_SCRIPT" "$@"
        ;;

    help|--help|-h)
        usage
        ;;

    "")
        if [[ ! -x "$PYTHON" ]]; then
            echo "[erro] Ambiente Python não encontrado."
            echo
            echo "Execute primeiro:"
            echo "  $ROOT_DIR/scripts/setup.sh"
            exit 1
        fi

        cd "$BACKEND_DIR"

        exec "$PYTHON" -m app.cli.main
        ;;

    *)
        echo "[erro] Comando desconhecido: $command"
        echo
        usage
        exit 1
        ;;
esac
