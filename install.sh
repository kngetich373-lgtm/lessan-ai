#!/usr/bin/env bash
# Lessan AI — one-command Linux installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/kngetich373-lgtm/lessan-ai/stabilize/provider-routing-ui/install.sh | bash
#
# The installer is intentionally user-local: no sudo is required.
set -euo pipefail

REPO_URL="https://github.com/kngetich373-lgtm/lessan-ai.git"
BRANCH="stabilize/provider-routing-ui"
APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/lessan"
SOURCE_DIR="$APP_HOME/source"
VENV_DIR="$APP_HOME/venv"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="$BIN_DIR/lessan-ai"
DESKTOP_FILE="$DESKTOP_DIR/com.lessan.ai.desktop"

info() { printf '\033[1;36m[Lessan]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[Lessan]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[Lessan] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "This installer currently supports Linux only."
command -v python3 >/dev/null 2>&1 || die "python3 is required."
command -v git >/dev/null 2>&1 || die "git is required."

PYTHON="$(command -v python3)"
mkdir -p "$APP_HOME" "$BIN_DIR" "$DESKTOP_DIR"

info "Installing Lessan AI for $USER"
info "Application data: $APP_HOME"

if [ -d "$SOURCE_DIR/.git" ]; then
    info "Updating existing Lessan source..."
    git -C "$SOURCE_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$SOURCE_DIR" checkout -q "$BRANCH"
    git -C "$SOURCE_DIR" reset --hard -q "origin/$BRANCH"
else
    info "Downloading Lessan AI..."
    rm -rf "$SOURCE_DIR.tmp"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$SOURCE_DIR.tmp"
    mv "$SOURCE_DIR.tmp" "$SOURCE_DIR"
fi

[ -f "$SOURCE_DIR/main.py" ] || die "Lessan entry point main.py was not found in the repository."

if [ ! -x "$VENV_DIR/bin/python" ]; then
    info "Creating Python virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR" || die "Could not create the Python virtual environment. Install python3-venv and retry."
fi

VENV_PY="$VENV_DIR/bin/python"
info "Installing Python dependencies..."
"$VENV_PY" -m pip install --upgrade pip wheel setuptools >/dev/null
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    "$VENV_PY" -m pip install -r "$SOURCE_DIR/requirements.txt"
fi

# Keep the repository installer available for `lessan-ai --update`.
cp -f "$SOURCE_DIR/install.sh" "$APP_HOME/install.sh"
chmod 755 "$APP_HOME/install.sh"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
APP_HOME="${APP_HOME}"
SOURCE_DIR="${SOURCE_DIR}"
VENV_PY="${VENV_DIR}/bin/python"

if [ "\${1:-}" = "--update" ]; then
    exec "\$APP_HOME/install.sh"
fi

[ -x "\$VENV_PY" ] || { echo "Lessan virtualenv is missing. Run the installer again." >&2; exit 1; }
cd "\$SOURCE_DIR"
exec "\$VENV_PY" "\$SOURCE_DIR/main.py" "\$@"
EOF
chmod 755 "$LAUNCHER"

ICON="$SOURCE_DIR/packaging/usr/share/icons/hicolor/scalable/apps/lessan-ai.svg"
ICON_PATH=""
if [ -f "$ICON" ]; then
    ICON_DIR="$DESKTOP_DIR/icons"
    mkdir -p "$ICON_DIR"
    cp -f "$ICON" "$ICON_DIR/lessan-ai.svg"
    ICON_PATH="$ICON_DIR/lessan-ai.svg"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Lessan AI
GenericName=AI Engineering Operating System
Comment=Lessan AI — AI Engineering Operating System
Exec=$LAUNCHER
TryExec=$LAUNCHER
Terminal=false
StartupNotify=true
Categories=Development;Utility;ArtificialIntelligence;
EOF
if [ -n "$ICON_PATH" ]; then
    printf 'Icon=%s\n' "$ICON_PATH" >> "$DESKTOP_FILE"
fi
chmod 644 "$DESKTOP_FILE"

case ":${PATH}:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not currently in PATH."; warn "Add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

info "Installation complete."
echo
echo "  Launch:        $LAUNCHER"
echo "  Or command:   lessan-ai"
echo "  Update:        lessan-ai --update"
echo "  App menu:      Lessan AI"
echo
echo "If 'lessan-ai' is not found, open a new terminal or add:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
