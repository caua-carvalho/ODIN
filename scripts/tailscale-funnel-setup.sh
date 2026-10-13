#!/usr/bin/env bash
#
# Permanent public URL for Odin WITHOUT owning a domain, using Tailscale Funnel.
#
#   ./scripts/tailscale-funnel-setup.sh [port]
#
# Runs tailscaled in userspace mode as a systemd --user service (no sudo, no
# TUN device) and exposes http://127.0.0.1:<port> at
# https://<hostname>.<tailnet>.ts.net — a fixed, free, HTTPS URL.
#
# Interactive steps you must complete in the browser when prompted:
#   1. Log in / approve the device (`tailscale up` prints a URL).
#   2. Enable Funnel for the tailnet the first time.
#
# Persistence: the unit is enabled and the machine already has Linger=yes, so
# both tailscaled and the Funnel survive logout/reboot.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOSTNAME_TS="${ODIN_TS_HOSTNAME:-odin}"

TS_DIR="$HOME/.local/opt/tailscale"
STATE_DIR="$HOME/.local/state/tailscale"
RUN_DIR="$HOME/.local/run/tailscale"
SOCK="$RUN_DIR/tailscaled.sock"
UNIT="$HOME/.config/systemd/user/tailscaled.service"
CLI_WRAPPER="$HOME/.local/bin/tailscale"

# Port: argument > ODIN_PORT from .env > 8000.
PORT="${1:-}"
if [[ -z "$PORT" ]]; then
    PORT="$(grep -E '^[[:space:]]*ODIN_PORT=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
fi
PORT="${PORT:-8000}"

install_binaries() {
    if [[ -x "$TS_DIR/tailscaled" ]]; then
        return
    fi
    echo "[odin] Baixando Tailscale (estático, sem sudo)..."
    local ver tmp
    tmp="$(mktemp -d)"
    ver="$(curl -fsSL 'https://pkgs.tailscale.com/stable/' \
        | grep -oE 'tailscale_[0-9.]+_amd64\.tgz' | head -1 | sed -E 's/tailscale_([0-9.]+)_amd64\.tgz/\1/')"
    curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${ver}_amd64.tgz" -o "$tmp/ts.tgz"
    mkdir -p "$HOME/.local/opt"
    tar -xzf "$tmp/ts.tgz" -C "$tmp"
    rm -rf "$TS_DIR"
    mv "$tmp/tailscale_${ver}_amd64" "$TS_DIR"
    rm -rf "$tmp"
    echo "[ok] Tailscale $ver instalado em $TS_DIR"
}

write_cli_wrapper() {
    mkdir -p "$(dirname "$CLI_WRAPPER")"
    cat > "$CLI_WRAPPER" <<EOF
#!/usr/bin/env bash
exec "$TS_DIR/tailscale" --socket="$SOCK" "\$@"
EOF
    chmod +x "$CLI_WRAPPER"
}

write_unit() {
    mkdir -p "$(dirname "$UNIT")" "$STATE_DIR" "$RUN_DIR"
    cat > "$UNIT" <<EOF
[Unit]
Description=Tailscale userspace daemon (for Odin Funnel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$TS_DIR/tailscaled --tun=userspace-networking --statedir=$STATE_DIR --socket=$SOCK
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
}

install_binaries
write_cli_wrapper
write_unit

systemctl --user daemon-reload
systemctl --user enable --now tailscaled.service
sleep 3

echo "[odin] Autenticando na Tailscale (siga o link abaixo no navegador)..."
if ! "$CLI_WRAPPER" status >/dev/null 2>&1; then
    :
fi
# `tailscale up` is idempotent: it prints a login URL only when needed.
"$CLI_WRAPPER" up --hostname="$HOSTNAME_TS" --accept-routes=false || true

echo
echo "[odin] Habilitando Funnel para a porta ${PORT}..."
echo "       (na primeira vez, aprove em https://login.tailscale.com/f/funnel?node=...)"
"$CLI_WRAPPER" funnel --bg "$PORT"

DNS="$("$CLI_WRAPPER" status --json 2>/dev/null | grep -m1 '"DNSName"' | cut -d'"' -f4 | sed 's/\.$//')"
echo
echo "[ok] Funnel ativo."
[[ -n "$DNS" ]] && echo "     URL pública: https://$DNS"
echo "     Status:      $CLI_WRAPPER serve status"
echo "     Desligar:    $CLI_WRAPPER funnel --https=443 off"
