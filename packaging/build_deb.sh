#!/bin/bash
# build_deb.sh — Build the Lessan AI .deb for Kali/Linux
# Usage: bash packaging/build_deb.sh -> lessan-ai_1.0.1-6_amd64.deb
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="$ROOT_DIR/packaging"
PAYLOAD_DIR="$PKG_DIR/opt/lessan-ai"
DEB_NAME="lessan-ai_1.0.1-6_amd64.deb"
DEB_PATH="$ROOT_DIR/$DEB_NAME"
HICOLOR="$PKG_DIR/usr/share/icons/hicolor"
ICON_SVG="$HICOLOR/scalable/apps/lessan-ai.svg"

echo "==> Building $DEB_NAME"

echo "==> Staging source into $PAYLOAD_DIR ..."
mkdir -p "$PAYLOAD_DIR"

# Runtime entrypoints and top-level modules.
for item in main.py lessan_ui.py omniroute.py or_client.py requirements.txt setup.py readme.md; do
    [ -e "$ROOT_DIR/$item" ] && cp -a "$ROOT_DIR/$item" "$PAYLOAD_DIR/"
done

# Runtime packages. Keep this list explicit so a new import cannot silently
# disappear from the Debian payload. In particular, documents/ is imported by
# main.py and was previously omitted, causing ModuleNotFoundError at startup.
for dir in actions agent core memory config scripts ui documents plugins workspaces; do
    [ -d "$ROOT_DIR/$dir" ] || continue
    mkdir -p "$PAYLOAD_DIR/$dir"
    rsync -a --delete \
        --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
        --exclude 'ms-playwright' \
        "$ROOT_DIR/$dir/" "$PAYLOAD_DIR/$dir/"
done

mkdir -p "$PAYLOAD_DIR/memory" "$PAYLOAD_DIR/reports"
rm -rf "$PAYLOAD_DIR/.venv" "$PAYLOAD_DIR/ms-playwright"
find "$PAYLOAD_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# NEVER ship real API keys or personal runtime state.
rm -f "$PAYLOAD_DIR/config/api_keys.json"
cat > "$PAYLOAD_DIR/config/api_keys.json.dist" <<'DIST'
{
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "os_system": "linux",
    "camera_index": 0
}
DIST
find "$PAYLOAD_DIR/memory" -maxdepth 1 -name '*.json' -delete 2>/dev/null || true
find "$PAYLOAD_DIR/reports" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$PAYLOAD_DIR/memory" "$PAYLOAD_DIR/reports"

echo "1.0.1-6" > "$PAYLOAD_DIR/VERSION"

echo "==> Normalizing payload permissions ..."
chmod -R a+rX "$PAYLOAD_DIR"

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

if [ ! -f "$PAYLOAD_DIR/face.png" ] && [ -f "$HICOLOR/256x256/apps/lessan-ai.png" ]; then
    cp -a "$HICOLOR/256x256/apps/lessan-ai.png" "$PAYLOAD_DIR/face.png"
    chmod a+r "$PAYLOAD_DIR/face.png"
fi

chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/postrm"
chmod 755 "$PKG_DIR/usr/bin/lessan-ai"
chmod 755 "$PKG_DIR/usr/lib/systemd/system-sleep/lessan-ai-resume"

echo "==> Building .deb with dpkg-deb ..."
rm -f "$DEB_PATH"
dpkg-deb --build --root-owner-group "$PKG_DIR" "$DEB_PATH"

echo "==> Verifying package ..."
dpkg-deb --info "$DEB_PATH"
echo "---- critical runtime files ----"
dpkg-deb --contents "$DEB_PATH" | grep -E '/opt/lessan-ai/(main.py|lessan_ui.py|documents/action.py|documents/__init__.py|VERSION)$'
echo ""
echo "==> Done: $DEB_PATH"
echo "    Install with: sudo apt install ./$(basename "$DEB_PATH")"
