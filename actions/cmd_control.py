# actions/cmd_control.py
# Lessan AI — Command / Open-File Controller (Kali/Linux optimized)
#
# Handles three kinds of requests:
#   1. "open <path/filename>"           -> opens with the OS default app
#   2. literal shell command (command)   -> runs it via /bin/bash -lc
#   3. natural-language task            -> runs as a shell command
#
# Behavior on Linux/Kali:
#   - `background=True`  -> launches GUI/long-running apps with Popen
#     (e.g. wireshark) and returns immediately.
#   - `visible=True`     -> tries a real terminal emulator; falls back to
#     background mode if none is installed.
#   - default (hidden)   -> captures stdout+stderr (up to 2000 chars) with a
#     120s timeout so tools like tshark can actually produce output.

import re
import subprocess
import platform
from pathlib import Path

from actions.terminal_utils import kitty_launch_split, run_with_sudo
from memory.config_manager import get_sudo_password

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _get_desktop() -> Path:
    home = Path.home()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def _find_candidate_path(task: str) -> Path | None:
    """Pull a file path or filename out of a natural-language task."""
    # Direct absolute/relative path mentioned in the task
    quoted = re.search(r'["\']([^"\']+)["\']', task)
    if quoted:
        candidate = Path(quoted.group(1)).expanduser()
        if candidate.exists():
            return candidate

    # Look for a token that looks like "name.ext"
    match = re.search(r'([A-Za-z0-9_\-\.\/\\]+\.[A-Za-z0-9]{1,6})', task)
    if match:
        name = match.group(1)
        search_dirs = [
            _get_desktop(),
            Path.home() / "Downloads",
            Path.home() / "Documents",
            Path.home(),
        ]
        for d in search_dirs:
            candidate = d / name
            if candidate.exists():
                return candidate
        # Maybe it's already a full path
        candidate = Path(name).expanduser()
        if candidate.exists():
            return candidate

    return None


def _open_with_default_app(path: Path) -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import os
            os.startfile(str(path))  # noqa: reached only on Windows
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:  # Linux / Kali
            # xdg-open is the standard; fall back to a direct spawn for
            # known-safe files if xdg-open is missing.
            if subprocess.run(["which", "xdg-open"], capture_output=True).returncode == 0:
                subprocess.Popen(["xdg-open", str(path)])
            else:
                subprocess.Popen([str(path)])
        return f"Opened {path.name}."
    except Exception as e:
        return f"Could not open {path.name}: {e}"


def _detect_gui_app(task: str) -> str | None:
    """Map common natural-language 'run X' phrases to known GUI apps."""
    low = task.strip().lower()
    # GUI-only applications. CLI tools (tshark, nmap, msfconsole) are NOT here —
    # they go through _run_capture so their output can be returned to the user.
    known = {
        "wireshark":     "wireshark",
        "wireshark gui": "wireshark",
        "burp suite":    "burpsuite",
        "burpsuite":     "burpsuite",
        "zenmap":        "zenmap",
        "filezilla":     "filezilla",
        "terminator":    "terminator",
        "kali terminal": "kitty",
        "terminal":      "kitty",
    }
    if low in known:
        return known[low]
    # "run wireshark" / "open wireshark" / "start wireshark"
    m = re.match(r"^(?:run|open|start|launch)\s+(.+)$", low)
    if m and m.group(1).strip() in known:
        return known[m.group(1).strip()]
    # Substring match: "run wireshark and show me the packets" -> wireshark
    for name in known:
        if name in low and name not in ("kali terminal", "wireshark gui"):
            return known[name]
    return None


def _detect_packet_capture(task: str) -> str | None:
    """Return a tshark command when the user asks to see/capture packets."""
    low = task.strip().lower()
    mentions_capture = any(k in low for k in (
        "capture", "packet", "packets", "sniff", "show me the packets",
        "show packets", "network traffic", "traffic",
    ))
    # Must actually be about wireshark/tshark/network, not e.g. "show me my packets sent"
    mentions_tool = any(k in low for k in ("wireshark", "tshark", "sniff", "capture"))
    if not (mentions_capture and mentions_tool):
        return None

    # Pull an interface out of "interface eth0" / "on eth0" / "-i eth0"
    iface = None
    m = re.search(r"(?:interface|on)\s+([a-zA-Z0-9_]+)", low)
    if m:
        iface = m.group(1)
    # Pull a packet count out of "10 packets" / "capture 10"
    count = None
    m = re.search(r"(\d+)\s*packets?", low)
    if m:
        count = m.group(1)

    cmd = ["tshark"]
    if iface:
        cmd += ["-i", iface]
    if count:
        cmd += ["-c", count]
    else:
        cmd += ["-c", "10"]
    return " ".join(cmd)


def _find_terminal() -> list[str] | None:
    """Find an installed terminal emulator appropriate for Kali (kitty preferred)."""
    candidates = [
        ["kitty"],                       # user's terminal — `kitty [--hold] cmd`
        ["x-terminal-emulator"],
        ["xfce4-terminal", "-e"],
        ["gnome-terminal", "--"],
        ["konsole", "-e"],
        ["mate-terminal", "-e"],
        ["lxterminal", "-e"],
        ["xterm", "-e"],
    ]
    for cmd in candidates:
        try:
            r = subprocess.run(["which", cmd[0]], capture_output=True, timeout=5)
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def _run_in_terminal(command: str) -> str:
    """Launch a command in a visible terminal emulator (kitty preferred).

    The command runs with a brief auto-close delay so the window closes on
    its own after the command finishes instead of waiting for a keypress.
    """
    wrapped = f"{command}; ec=$?; echo; echo 'Exit code: $ec'; sleep 3; exit $ec"
    term = _find_terminal()
    if term is None:
        return None  # signal fallback to background mode
    try:
        if term[0] == "kitty":
            # Prefer a split window inside the running kitty session.
            ok, detail = kitty_launch_split(["bash", "-c", wrapped])
            if ok:
                return f"Running command in a kitty split window ({detail}): {command}"
            # Fall back to a standalone kitty window. kitty closes the window
            # automatically when the shell exits, so no --hold is needed.
            subprocess.Popen(["kitty", "bash", "-c", wrapped])
            return f"Running command in a kitty window: {command}"
        if term[0] == "x-terminal-emulator":
            # Debian wrapper — pass through the wrapped command
            subprocess.Popen([term[0], "-e", "bash", "-c", wrapped])
        elif term[0] == "gnome-terminal":
            subprocess.Popen([term[0], "--", "bash", "-c", wrapped])
        else:
            subprocess.Popen(term + ["bash", "-c", wrapped])
        return f"Running command in a terminal: {command}"
    except Exception as e:
        return f"Could not run command in a terminal: {e}"


def _open_kitty_shell() -> str:
    """Open a fresh shell in kitty — as a split window inside the current kitty
    session when possible, otherwise in a new standalone kitty window."""
    ok, detail = kitty_launch_split([])
    if ok:
        return f"Opened a terminal in a kitty split window ({detail})."
    try:
        subprocess.Popen(["kitty"])
        return "Opened a kitty terminal window."
    except Exception as e:
        return f"Could not open a terminal: {e}"


def _run_background(command: str) -> str:
    """Launch a GUI/long-running command detached from Lessan."""
    try:
        subprocess.Popen(
            ["/bin/bash", "-lc", command],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path.home()),
        )
        return f"Launched in background: {command}"
    except Exception as e:
        return f"Could not launch in background: {e}"


def _run_capture(command: str) -> str:
    """Run a quick command and capture its output (up to 2000 chars)."""
    try:
        stripped = command.strip()
        if stripped.startswith("sudo ") and get_sudo_password():
            # A default sudo password is configured — pipe it in via
            # run_with_sudo so privileged installs never block on a prompt.
            _code, out, err = run_with_sudo(stripped[len("sudo "):].strip())
            output, error = out, err
        else:
            result = subprocess.run(
                ["/bin/bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(Path.home()),
            )
            output = (result.stdout or "").strip()
            error  = (result.stderr or "").strip()
        if output and error:
            output = f"{output}\n[stderr] {error}"
        elif error:
            output = error
        if not output:
            output = "Command completed with no output."
        return output[:2000]
    except subprocess.TimeoutExpired:
        return f"Command timed out after 120 seconds: {command}"
    except Exception as e:
        return f"Command failed: {e}"


def _run_shell_command(task: str, visible: bool = False, background: bool = False) -> str:
    # Carry over the working directory? We always run in $HOME via bash -lc.
    command = task.strip()
    if not command:
        return "Empty command."

    # If the user asked to see/capture packets ("run wireshark and show me
    # the packets"), run a tshark capture and return the packet output.
    # If they ALSO mentioned a GUI app (e.g. wireshark), launch it too.
    packet_cmd = _detect_packet_capture(command)
    if packet_cmd and not visible:
        gui_app = _detect_gui_app(command)
        if gui_app and not background:
            _run_background(gui_app)
        return _run_capture(packet_cmd)

    # Strip natural-language wrapper words if present
    low = command.lower()
    m = re.match(r"^(?:run|open|start|launch|execute|do)\s+(.+)$", low)
    if m:
        command = m.group(1).strip()

    # If it's clearly a GUI app request, launch in background automatically.
    # "terminal" / "kali terminal" resolve to kitty and open a kitty split
    # window inside the current session instead of a bare background process.
    gui_app = _detect_gui_app(command)
    if gui_app and (background or not visible):
        if gui_app == "kitty":
            return _open_kitty_shell()
        return _run_background(gui_app)

    if visible:
        res = _run_in_terminal(command)
        if res is not None:
            return res
        # No terminal emulator found — fall back to background
        return _run_background(command)

    if background:
        return _run_background(command)

    return _run_capture(command)


def cmd_control(parameters: dict, player=None) -> str:
    task       = (parameters or {}).get("task", "").strip()
    command    = (parameters or {}).get("command", "").strip()
    visible    = bool((parameters or {}).get("visible", False))
    background = bool((parameters or {}).get("background", False))

    # Prefer the explicit literal command if provided
    if command:
        task = command

    if not task:
        return "cmd_control requires a 'task' or 'command' description."

    result = "Unknown command."
    try:
        if task.lower().startswith("open "):
            candidate = _find_candidate_path(task)
            if candidate:
                result = _open_with_default_app(candidate)
            else:
                # Maybe "open wireshark" style
                gui = _detect_gui_app(task)
                if gui:
                    if gui == "kitty":
                        result = _open_kitty_shell()
                    else:
                        result = _run_background(gui)
                else:
                    result = f"Could not find a file matching: {task}"
        else:
            result = _run_shell_command(task, visible=visible, background=background)
    except Exception as e:
        result = f"cmd_control error: {e}"

    if player:
        player.write_log(f"[cmd] {result[:60]}")

    print(f"[cmd_control] {task[:50]} -> {result[:100]}")
    return result