#!/usr/bin/env bash
#
# Install (or reinstall) the Odin backend as a systemd *system* service.
#
# This is the hosting-oriented unit: it restarts on failure and hardens the
# service (ProtectSystem=strict, ProtectHome, …), unlike
# scripts/install-autostart.sh which installs a desktop `--user` unit. Requires
# sudo.
#
#   sudo ./scripts/install-service.sh [--user <name>] [--workspace <path>]
#   ./scripts/install-service.sh --print        # render to stdout, no sudo
#
# Defaults: user = the user who invoked sudo, workspace = ODIN_WORKSPACE from
# .env (or ~/odin-workspace). For a true privilege split pass a dedicated
# account, e.g. `--user odin` (see README.deploy.md → "Usuário dedicado").

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/deploy/odin.service"
UNIT_DEST="/etc/systemd/system/odin.service"

RUN_USER="${SUDO_USER:-$(whoami)}"
WORKSPACE=""
PRINT_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) RUN_USER="$2"; shift 2 ;;
        --workspace) WORKSPACE="$2"; shift 2 ;;
        --print) PRINT_ONLY=1; shift ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ "$PRINT_ONLY" -eq 0 && "${EUID}" -ne 0 ]]; then
    echo "[erro] Rode com sudo: sudo $0   (ou use --print para só visualizar)" >&2
    exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "[erro] $ROOT_DIR/.env não encontrado. Copie .env.production.example primeiro." >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "[erro] Template não encontrado: $TEMPLATE" >&2
    exit 1
fi

if [[ -z "$WORKSPACE" ]]; then
    WORKSPACE="$(grep -E '^[[:space:]]*ODIN_WORKSPACE=' "$ROOT_DIR/.env" | tail -n1 | cut -d= -f2- || true)"
fi
WORKSPACE="${WORKSPACE:-$HOME/odin-workspace}"

# --- Sandbox rendering (matches deploy/odin.service, issue #14) --------------
# Full home isolation ("true") hides /home, /root and /run/user entirely. That
# breaks a deployment whose checkout or workspace lives under a user's home, so
# fall back to "read-only" there — ReadWritePaths still carves out the writable
# paths below.
PROTECT_HOME="true"
for candidate in "$ROOT_DIR" "$WORKSPACE"; do
    case "$candidate" in
        /home/*|/root/*|/run/user/*) PROTECT_HOME="read-only" ;;
    esac
done

# ProtectSystem=strict makes the whole filesystem read-only, so anything the app
# writes to outside the repo + workspace must be listed in ReadWritePaths. The
# default DB (a relative sqlite path) is already inside the repo; only absolute
# locations need an extra entry.
_abs_dir_from_env() {
    local value dir out=""
    value="$(grep -E "^[[:space:]]*$1=" "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    if [[ -n "$value" ]]; then
        # sqlite URLs: ":///relative" stays inside the repo, ":////absolute" not.
        dir="${value#*:///}"
        if [[ "$dir" == /* ]]; then
            out="$(dirname "$dir")"
        fi
    fi
    printf '%s' "$out"
}
EXTRA_READ_WRITE_PATHS=""
for _key in DATABASE_URL ODIN_MEMORY_PATH; do
    _dir="$(_abs_dir_from_env "$_key")"
    case " $EXTRA_READ_WRITE_PATHS " in
        *" $_dir "*) ;;  # already added by another setting
        *) [[ -n "$_dir" ]] && EXTRA_READ_WRITE_PATHS="${EXTRA_READ_WRITE_PATHS} ${_dir}" ;;
    esac
done
EXTRA_READ_WRITE_PATHS="${EXTRA_READ_WRITE_PATHS# }"

render() {
    sed \
        -e "s|__ODIN_ROOT__|$ROOT_DIR|g" \
        -e "s|__ODIN_USER__|$RUN_USER|g" \
        -e "s|__ODIN_WORKSPACE__|$WORKSPACE|g" \
        -e "s|__PROTECT_HOME__|$PROTECT_HOME|g" \
        -e "s|__EXTRA_READ_WRITE_PATHS__|$EXTRA_READ_WRITE_PATHS|g" \
        "$TEMPLATE"
}

RENDERED="$(render)"
if grep -qE '__(ODIN_ROOT|ODIN_USER|ODIN_WORKSPACE|PROTECT_HOME|EXTRA_READ_WRITE_PATHS)__' <<<"$RENDERED"; then
    echo "[erro] Placeholder não renderizado no unit. Abortando." >&2
    exit 1
fi

if [[ "$PRINT_ONLY" -eq 1 ]]; then
    echo "[odin] Sandbox: ProtectSystem=strict, ProtectHome=$PROTECT_HOME${EXTRA_READ_WRITE_PATHS:+, extras: $EXTRA_READ_WRITE_PATHS}" >&2
    printf '%s\n' "$RENDERED"
    exit 0
fi

echo "[odin] Renderizando unit para usuário '$RUN_USER', workspace '$WORKSPACE'"
echo "[odin] Sandbox: ProtectSystem=strict, ProtectHome=$PROTECT_HOME"
if [[ -n "$EXTRA_READ_WRITE_PATHS" ]]; then
    echo "[odin] Caminhos graváveis extras: $EXTRA_READ_WRITE_PATHS"
fi

printf '%s\n' "$RENDERED" > "$UNIT_DEST"

mkdir -p "$WORKSPACE"
chown "$RUN_USER":"$RUN_USER" "$WORKSPACE" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now odin.service

echo "[ok] Serviço instalado: $UNIT_DEST"
echo "     Status:  systemctl status odin.service"
echo "     Logs:    journalctl -u odin.service -f"
echo "     Sandbox: systemd-analyze security odin.service"
