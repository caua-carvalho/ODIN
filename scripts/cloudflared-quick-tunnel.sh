#!/usr/bin/env bash
#
# Fastest way to reach Odin from your phone and the web panel: a Cloudflare
# *quick* tunnel. It prints a public https://<random>.trycloudflare.com URL in
# a few seconds — no domain, no DNS, no open port, no config.
#
#   ./scripts/cloudflared-quick-tunnel.sh
#
# Caveats:
#   * The URL changes every time you restart this command.
#   * There is no Cloudflare Access login in front of it, so the ONLY thing
#     protecting the API is ODIN_API_TOKEN. Make sure it is set (see below).
#   * The panel HTML is public; the API calls need the token.
#
# For a stable URL + login, use the named tunnel flow in README.deploy.md.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
CF_BIN="$BIN_DIR/cloudflared"

# Port: prefer ODIN_PORT from .env, else 8000.
PORT="$(grep -E '^[[:space:]]*ODIN_PORT=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
PORT="${ODIN_PORT:-${PORT:-8000}}"

warn_token() {
    local token
    token="$(grep -E '^[[:space:]]*ODIN_API_TOKEN=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    if [[ -z "$token" ]]; then
        echo "[aviso] ODIN_API_TOKEN está vazio no .env — a API ficaria ABERTA na"
        echo "        internet. Gere um (openssl rand -hex 32), cole no .env e"
        echo "        reinicie o backend antes de continuar."
        echo
    fi
}

install_cloudflared() {
    if command -v cloudflared >/dev/null 2>&1; then
        CF_BIN="$(command -v cloudflared)"
        return
    fi
    if [[ -x "$CF_BIN" ]]; then
        return
    fi

    local arch asset
    case "$(uname -m)" in
        x86_64|amd64) arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
        armv7l) arch="arm" ;;
        *) echo "[erro] Arquitetura não suportada: $(uname -m)" >&2; exit 1 ;;
    esac
    asset="cloudflared-linux-${arch}"

    echo "[odin] Instalando cloudflared em $CF_BIN (sem sudo)..."
    mkdir -p "$BIN_DIR"
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${asset}" -o "$CF_BIN"
    chmod +x "$CF_BIN"
    echo "[ok] cloudflared instalado."
}

install_cloudflared
warn_token

if ! curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    echo "[aviso] http://127.0.0.1:${PORT}/api/health não respondeu."
    echo "        Garanta que o backend está no ar (odin start / systemctl start odin)."
    echo
fi

echo "[odin] Abrindo túnel rápido para http://127.0.0.1:${PORT} ..."
echo "       Copie a URL https://xxxx.trycloudflare.com que aparecer abaixo."
echo "       Painel web: defina localStorage['odin_api_token'] = <seu token>."
echo "       App mobile: Server URL = essa URL  +  o mesmo token."
echo

exec "$CF_BIN" tunnel --url "http://127.0.0.1:${PORT}"
