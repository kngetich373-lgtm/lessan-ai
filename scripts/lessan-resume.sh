#!/bin/bash
# ============================================================
#  lessan-resume.sh
#  Launch the Lessan AI assistant after the laptop wakes up.
#
#  Invoked by /etc/systemd/system-sleep/lessan-resume (which is
#  called by systemd with argument "post" after resume from
#  suspend). Also safe to run manually:
#      ~/Lessan/scripts/lessan-resume.sh
# ============================================================

LESSAN_DIR="${LESSAN_DIR:-$HOME/Lessan}"
LOG="/tmp/lessan-resume.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

# Let the desktop session settle after resume (sound server, etc.).
sleep 6

# --- Desktop / session environment --------------------------------
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# Sound: pipewire/pulse user socket lives under $XDG_RUNTIME_DIR.
if [ -z "$PULSE_SERVER" ] && [ -S "$XDG_RUNTIME_DIR/pulse/native" ]; then
    export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
fi

# DBus session bus (needed for session integration).
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

# --- Already running? ---------------------------------------------
if pgrep -f "Lessan/main.py" >/dev/null 2>&1; then
    log "Lessan already running — skipping."
    exit 0
fi

# --- Launch --------------------------------------------------------
if [ ! -x "$LESSAN_DIR/lessan.sh" ]; then
    log "ERROR: $LESSAN_DIR/lessan.sh not found or not executable."
    exit 1
fi

log "Launching Lessan (DISPLAY=$DISPLAY, PULSE_SERVER=$PULSE_SERVER)..."
setsid nohup "$LESSAN_DIR/lessan.sh" >> "$LOG" 2>&1 < /dev/null &
disown
sleep 1
if pgrep -f "Lessan/main.py" >/dev/null 2>&1; then
    log "Lessan started successfully."
else
    log "WARNING: Lessan may not have started; check the log above."
fi
exit 0