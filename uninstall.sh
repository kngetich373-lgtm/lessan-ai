#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/lessan"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

rm -f "$BIN_DIR/lessan-ai"
rm -f "$DESKTOP_DIR/com.lessan.ai.desktop"
rm -rf "$APP_HOME"

printf 'Lessan AI user-local installation removed.\n'
printf 'System-wide .deb installations are not modified by this script.\n'
