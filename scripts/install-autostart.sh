#!/usr/bin/env bash
#
# Installs (or reinstalls) Odin autostart:
#   * a systemd --user unit that starts the backend (and therefore the web
#     panel, which is served by the backend) at boot, even before login;
#   * an XDG desktop autostart entry that opens the panel in the browser on
#     login (used by GNOME/KDE/XFCE and other XDG-autostart desktops);
#   * a Hyprland exec hook for ~/.config/hypr/custom/execs.lua, because
#     Hyprland ignores ~/.config/autostart.
#
# Re-running this script is safe: it overwrites the generated files.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SYSTEMD_USER_DIR="$CONFIG_HOME/systemd/user"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
UNIT="$SYSTEMD_USER_DIR/odin.service"
DESKTOP_ENTRY="$AUTOSTART_DIR/odin-panel.desktop"
HYPR_EXECS="$CONFIG_HOME/hypr/custom/execs.lua"

mkdir -p "$SYSTEMD_USER_DIR" "$AUTOSTART_DIR"
chmod +x "$ROOT_DIR/scripts/open-panel.sh"

# --- Backend: start at boot via systemd --user (needs lingering for boot) ---
cat > "$UNIT" <<EOF
[Unit]
Description=Odin Personal AI Assistant (backend + web panel)
Documentation=file://$ROOT_DIR/AGENTS.md
After=network-online.target
Wants=network-online.target

[Service]
# Type=forking + PIDFile lets systemd supervise the uvicorn process that
# scripts/server.sh backgrounds (nohup), so Restart=always actually works.
Type=forking
PIDFile=%S/odin/server.pid
WorkingDirectory=$ROOT_DIR
ExecStart=/usr/bin/env bash $ROOT_DIR/scripts/server.sh start
ExecStop=/usr/bin/env bash $ROOT_DIR/scripts/server.sh stop
Restart=always
RestartSec=3
TimeoutStartSec=180
TimeoutStopSec=60

[Install]
WantedBy=default.target
EOF

# --- Panel: open the browser on graphical login ---
cat > "$DESKTOP_ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Odin Panel
Comment=Abre o painel web do Odin
Exec=$ROOT_DIR/scripts/open-panel.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

# --- Hyprland: XDG autostart (~/.config/autostart) is NOT read by Hyprland,
#     so wire it into the compositor config as well. The dots config sources
#     ~/.config/hypr/custom/execs.lua, which is the file meant for user entries.
if [ -d "$CONFIG_HOME/hypr" ]; then
    mkdir -p "$(dirname "$HYPR_EXECS")"
    touch "$HYPR_EXECS"
    # Drop any previously managed block (idempotent re-runs).
    sed -i '/^-- >>> odin-autostart >>>$/,/^-- <<< odin-autostart <<<$/d' "$HYPR_EXECS"
    # The Hyprland hook must point at THIS clone, not at a hardcoded $HOME/odin,
    # so the panel opens on a checkout anywhere on disk. Escape the two
    # characters that are special inside a Lua string literal (backslash and
    # double quote) so a path with those still renders a valid hook.
    HYPR_OPEN_PANEL="$ROOT_DIR/scripts/open-panel.sh"
    HYPR_OPEN_PANEL="${HYPR_OPEN_PANEL//\\/\\\\}"
    HYPR_OPEN_PANEL="${HYPR_OPEN_PANEL//\"/\\\"}"
    cat >> "$HYPR_EXECS" <<EOF
-- >>> odin-autostart >>>
-- Managed by $ROOT_DIR/scripts/install-autostart.sh — do not edit by hand.
-- Opens the Odin web panel shortly after Hyprland starts (the backend itself
-- is started at boot by the systemd --user unit odin.service).
hl.on("hyprland.start", function()
    hl.exec_cmd("$HYPR_OPEN_PANEL")
end)
-- <<< odin-autostart <<<
EOF
    echo "[ok] Hyprland hook atualizado: $HYPR_EXECS"
fi

systemctl --user daemon-reload
systemctl --user enable --now odin.service

# Let the user service start at boot even when nobody has logged in yet.
if command -v loginctl >/dev/null 2>&1; then
    loginctl enable-linger "$USER" || true
fi

echo "[ok] Autostart instalado."
echo "     Unit:    $UNIT"
echo "     Desktop: $DESKTOP_ENTRY"
if [ -d "$CONFIG_HOME/hypr" ]; then
    echo "     Hyprland:$HYPR_EXECS"
fi
echo
echo "Verifique com:  systemctl --user status odin.service"
