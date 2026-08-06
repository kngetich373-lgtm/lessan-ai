# actions/terminal_utils.py
# Shared kitty-aware terminal helpers used by cmd_control.py and
# project_launcher.py. Keeps the remote-control logic in one place so
# commands launched inside the user's kitty session open as split windows
# in that same session (matching the "open a new window inside Lessan"
# behavior), with a standalone kitty window as fallback.

import os
import subprocess
from pathlib import Path

from memory.config_manager import get_sudo_password


def running_inside_kitty() -> bool:
    """True when the current process was launched inside a kitty session
    (kitty exports KITTY_PID to every child process)."""
    return bool(os.environ.get("KITTY_PID"))


def kitty_launch_split(cmd: list[str]) -> tuple[bool, str]:
    """Launch a command inside the user's running kitty instance as a split
    window. Returns (success, detail).

    Two mechanisms are used, in order of preference:
      1. Socket remote control — used when KITTY_LISTEN_ON is set (kitty
         exposes a control socket; clean, works even with captured stdio).
      2. Escape-sequence remote control — used when running inside a kitty
         session. Requires the child to keep its stdout attached to the PTY
         (kitty reads the control payload from the PTY master).
    """
    if os.environ.get("KITTY_LISTEN_ON"):
        try:
            r = subprocess.run(
                ["kitty", "@", "launch", "--location=vsplit"] + cmd,
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return True, "kitty control socket"
            return False, f"kitty socket error: {(r.stderr or '').strip()[:120]}"
        except Exception as e:
            return False, f"kitty socket unreachable: {e}"

    if running_inside_kitty():
        try:
            # Popen (no capture) so the escape-sequence control payload goes
            # out on the PTY that kitty listens to. Non-blocking.
            subprocess.Popen(["kitty", "@", "launch", "--location=vsplit"] + cmd)
            return True, "kitty escape-sequence"
        except Exception as e:
            return False, f"kitty remote control failed: {e}"

    return False, "not inside a kitty session"


def run_with_sudo(command: str) -> tuple[int, str, str]:
    """Run a privileged command, piping in the configured default sudo
    password when one is available so automated installs never block on an
    interactive password prompt.

    Returns (returncode, stdout, stderr). When no password is configured the
    command runs via plain `sudo <cmd>`, which may prompt interactively.
    """
    password = get_sudo_password()

    if password:
        shell_cmd = f"echo '{password}' | sudo -S {command}"
    else:
        shell_cmd = f"sudo {command}"

    try:
        r = subprocess.run(
            ["/bin/bash", "-lc", shell_cmd],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home()),
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out after 120 seconds."
    except Exception as e:
        return -1, "", f"Command failed: {e}"
