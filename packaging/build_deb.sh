#!/bin/bash
# build_deb.sh — Build the Lessan AI .deb for Kali/Linux
# Usage: bash packaging/build_deb.sh  ->  lessan-ai_1.0.1-3_amd64.deb
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="$ROOT_DIR/packaging"
PAYLOAD_DIR="$PKG_DIR/opt/lessan-ai"
DEB_NAME="lessan-ai_1.0.1-3_amd64.deb"
DEB_PATH="$ROOT_DIR/$DEB_NAME"
HICOLOR="$PKG_DIR/usr/share/icons/hicolor"
ICON_SVG="$HICOLOR/scalable/apps/lessan-ai.svg"

echo "==> Building $DEB_NAME"

# --- 1. Stage project source into payload (incremental, --delete keeps it
#         in sync with the repo on every build) ------------------------
echo "==> Staging source into $PAYLOAD_DIR ..."
mkdir -p "$PAYLOAD_DIR"
for item in main.py ui.py omniroute.py or_client.py requirements.txt setup.py readme.md; do
    [ -e "$ROOT_DIR/$item" ] && cp -a "$ROOT_DIR/$item" "$PAYLOAD_DIR/"
done
for dir in actions agent core memory config scripts; do
    [ -d "$ROOT_DIR/$dir" ] || continue
    mkdir -p "$PAYLOAD_DIR/$dir"
    rsync -a --delete \
        --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
        --exclude 'ms-playwright' \
        "$ROOT_DIR/$dir/" "$PAYLOAD_DIR/$dir/"
done

mkdir -p "$PAYLOAD_DIR/memory" "$PAYLOAD_DIR/reports"
# Never ship a venv/browsers even if a previous build polluted the payload.
rm -rf "$PAYLOAD_DIR/.venv" "$PAYLOAD_DIR/ms-playwright"
find "$PAYLOAD_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# NEVER ship real API keys or personal runtime state. This scrub runs on
# every build (even incremental) so stale/migrated data never leaks in.
rm -f "$PAYLOAD_DIR/config/api_keys.json"
cat > "$PAYLOAD_DIR/config/api_keys.json.dist" <<'DIST'
{
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "os_system": "linux",
    "camera_index": 0
}
DIST
# memory/ ships only Python modules; the conversation/long-term/reminder
# JSON files and the reports/ tree are per-user runtime data that MUST NOT
# be packaged (they migrate from ~/Lessan on first run instead).
find "$PAYLOAD_DIR/memory" -maxdepth 1 -name '*.json' -delete 2>/dev/null || true
find "$PAYLOAD_DIR/reports" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$PAYLOAD_DIR/memory" "$PAYLOAD_DIR/reports"

echo "1.0.1-3" > "$PAYLOAD_DIR/VERSION"

# --- 2. Normalize payload permissions -------------------------------
# Source files are often mode 0600 (from umask). Blow away any such modes
# so the installed /opt/lessan-ai is world-readable and the desktop user
# can rsync the bundle without "Permission denied". dpkg-deb
# --root-owner-group sets root:root ownership; a+rX = read for all,
# execute only where the original has an execute bit.
echo "==> Normalizing payload permissions ..."
chmod -R a+rX "$PAYLOAD_DIR"

# --- 3. Icon: rasterize the SVG to PNG sizes ----------------------
echo "==> Generating PNG icons from SVG ..."
for size in 48 128 256; do
    outdir="$HICOLOR/${size}x${size}/apps"
    mkdir -p "$outdir"
    if command -v rsvg-convert >/dev/null 2>&1; then
        rsvg-convert -w "$size" -h "$size" -o "$outdir/lessan-ai.png" "$ICON_SVG"
    elif command -v convert >/dev/null 2>&1; then
        convert -background none -resize "${size}x${size}" "$ICON_SVG" "$outdir/lessan-ai.png"
    else
        echo "    !! neither rsvg-convert nor ImageMagick found; skipping ${size}px PNG"
        rm -f "$outdir/lessan-ai.png"
    fi
done

# Also a default face.png the UI renders on its orb (mirrors the icon orb).
if [ ! -f "$PAYLOAD_DIR/face.png" ] && [ -f "$HICOLOR/256x256/apps/lessan-ai.png" ]; then
    cp -a "$HICOLOR/256x256/apps/lessan-ai.png" "$PAYLOAD_DIR/face.png"
    chmod a+r "$PAYLOAD_DIR/face.png"
fi

# --- 4. Ensure executable bits ------------------------------------
chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/postrm"
chmod 755 "$PKG_DIR/usr/bin/lessan-ai"
chmod 755 "$PKG_DIR/usr/lib/systemd/system-sleep/lessan-ai-resume"

# --- 5. Build the archive ------------------------------------------
echo "==> Building .deb with dpkg-deb ..."
rm -f "$DEB_PATH"
dpkg-deb --build --root-owner-group "$PKG_DIR" "$DEB_PATH"

# --- 6. Verify ------------------------------------------------------
echo "==> Verifying package ..."
dpkg-deb --info "$DEB_PATH"
echo "---- file list (top level) ----"
dpkg-deb --contents "$DEB_PATH" | awk '{print $NF}' | grep -E "/(opt|usr|DEBIAN)/" | grep -v "/$" | head -40
echo ""
echo "==> Done: $DEB_PATH"
echo "    Install with:  sudo apt install ./$(basename "$DEB_PATH")"
