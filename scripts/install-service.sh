#!/usr/bin/env bash
#
# Install (or reinstall) the Odin backend as a systemd *system* service.
#
# This is the hosting-oriented unit: it restarts on failure and runs as a
# dedicated user, unlike scripts/install-autostart.sh which installs a desktop
# `--user` unit. Requires sudo.
#
#   sudo ./scripts/install-service.sh [--user <name>] [--workspace <path>]
#
# Defaults: user = the user who invoked sudo, workspace = ODIN_WORKSPACE from
# .env (or ~/odin-workspace).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/deploy/odin.service"
UNIT_DEST="/etc/systemd/system/odin.service"

RUN_USER="${SUDO_USER:-$(whoami)}"
WORKSPACE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) RUN_USER="$2"; shift 2 ;;
        --workspace) WORKSPACE="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ "${EUID}" -ne 0 ]]; then
    echo "[erro] Rode com sudo: sudo $0" >&2
    exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "[erro] $ROOT_DIR/.env não encontrado. Copie .env.production.example primeiro." >&2
    exit 1
fi

if [[ -z "$WORKSPACE" ]]; then
    WORKSPACE="$(grep -E '^[[:space:]]*ODIN_WORKSPACE=' "$ROOT_DIR/.env" | tail -n1 | cut -d= -f2- || true)"
fi
WORKSPACE="${WORKSPACE:-$HOME/odin-workspace}"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "[erro] Template não encontrado: $TEMPLATE" >&2
    exit 1
fi

echo "[odin] Renderizando unit para usuário '$RUN_USER', workspace '$WORKSPACE'"
sed \
    -e "s|__ODIN_ROOT__|$ROOT_DIR|g" \
    -e "s|__ODIN_USER__|$RUN_USER|g" \
    -e "s|__ODIN_WORKSPACE__|$WORKSPACE|g" \
    "$TEMPLATE" > "$UNIT_DEST"

mkdir -p "$WORKSPACE"
chown "$RUN_USER":"$RUN_USER" "$WORKSPACE" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now odin.service

echo "[ok] Serviço instalado: $UNIT_DEST"
echo "     Status:  systemctl status odin.service"
echo "     Logs:    journalctl -u odin.service -f"
