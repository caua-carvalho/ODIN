#!/usr/bin/env bash
#
# Build everything Odin needs to serve the web panel and run the API.
#
#   ./scripts/build.sh
#
# The backend serves the built panel from frontend/dist, so this must be run
# once (and again after every frontend change) before the service is useful.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON="$BACKEND_DIR/.venv/bin/python"

echo "[odin] Backend: criando venv e instalando dependências..."
if [[ ! -x "$PYTHON" ]]; then
    python3 -m venv "$BACKEND_DIR/.venv"
fi
"$BACKEND_DIR/.venv/bin/pip" install -q --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
echo "[ok] Backend pronto."

echo "[odin] Frontend: instalando dependências e buildando..."
cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
    npm install --silent
fi
npm run build
echo "[ok] Painel buildado em $FRONTEND_DIR/dist."

echo
echo "[ok] Build completo. Suba o serviço com:"
echo "     ./scripts/install-service.sh   (uma vez, com sudo)"
echo "     systemctl restart odin.service"
