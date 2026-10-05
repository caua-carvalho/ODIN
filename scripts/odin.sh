#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "[erro] Ambiente Python não encontrado."
    echo
    echo "Execute primeiro:"
    echo "  ./scripts/setup.sh"
    exit 1
fi

cd "$BACKEND_DIR"

exec "$PYTHON" -m app.cli.main