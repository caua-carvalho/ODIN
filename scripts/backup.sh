#!/usr/bin/env bash
#
# Back up Odin's SQLite database and workspace.
#
#   ./scripts/backup.sh [dest_dir]
#
# Default destination: ~/.local/state/odin/backups
# Keep this out of the workspace so the agent cannot see/delete its own backups.
# Run it from cron or a systemd timer.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DEST="${1:-${XDG_STATE_HOME:-$HOME/.local/state}/odin/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

PYTHON="$BACKEND_DIR/.venv/bin/python"

mkdir -p "$DEST"

# Workspace location from .env (fallback: ~/odin-workspace).
WORKSPACE="$(grep -E '^[[:space:]]*ODIN_WORKSPACE=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
WORKSPACE="${WORKSPACE:-$HOME/odin-workspace}"

DB_FILE="$BACKEND_DIR/odin.db"

# 1. Consistent SQLite backup (safe while the server is running).
if [[ -f "$DB_FILE" ]]; then
    if [[ -x "$PYTHON" ]]; then
        "$PYTHON" - "$DB_FILE" "$DEST/odin-$STAMP.db" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
con = sqlite3.connect(src)
with sqlite3.connect(dst) as out:
    con.backup(out)
con.close()
print(f"[ok] DB backupeado -> {dst}")
PY
    else
        cp "$DB_FILE" "$DEST/odin-$STAMP.db"
        echo "[ok] DB copiado -> $DEST/odin-$STAMP.db"
    fi
else
    echo "[aviso] $DB_FILE não encontrado; pulando backup do banco."
fi

# 2. Workspace files.
if [[ -d "$WORKSPACE" ]]; then
    tar -czf "$DEST/workspace-$STAMP.tar.gz" -C "$(dirname "$WORKSPACE")" "$(basename "$WORKSPACE")"
    echo "[ok] Workspace -> $DEST/workspace-$STAMP.tar.gz"
else
    echo "[aviso] Workspace $WORKSPACE não encontrado; pulando."
fi

# 3. Keep the last 14 of each.
ls -1t "$DEST"/odin-*.db 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t "$DEST"/workspace-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "[ok] Backup concluído em $DEST"
