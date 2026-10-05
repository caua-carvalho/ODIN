#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."

echo "========================================"
echo "  Odin Personal AI Assistant - Setup"
echo "========================================"

# Check .env
if [ ! -f "$ROOT/.env" ]; then
    echo "Creating .env from .env.example..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo ""
    echo "⚠️  IMPORTANT: Edit $ROOT/.env and add your GEMINI_API_KEY"
    echo ""
fi

# Backend setup
echo "Setting up Python backend..."
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Virtual environment created."
fi
.venv/bin/pip install -r requirements.txt -q
echo "✓ Backend dependencies installed"

# Workspace
mkdir -p "$ROOT/../odin-workspace"
echo "✓ Workspace directory ready: $(realpath $ROOT/../odin-workspace)"

# Frontend setup
echo "Setting up frontend..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    npm install --silent
fi
echo "✓ Frontend dependencies installed"

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your GEMINI_API_KEY"
echo "  2. Run: ./scripts/dev.sh"
echo ""
