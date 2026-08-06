# actions/project_launcher.py
# Finds a project folder by name (searching common dev locations),
# detects how to run it from marker files, and launches it in a
# visible terminal so the user can see output/errors.

import platform
import shutil
import subprocess
from pathlib import Path

from actions.terminal_utils import kitty_launch_split

# Folders searched, in order, when the user gives just a project name
# instead of a full path. Add your own here if your projects live
# somewhere else.
_SEARCH_ROOTS = [
    "projects", "Projects", "dev", "Development", "code", "Code",
    "repos", "Repositories", "workspace", "Documents", "Desktop",
]

# marker file -> command to run, checked in this order (first match wins)
_PROJECT_MARKERS = [
    ("docker-compose.yml", "docker compose up"),
    ("compose.yml",        "docker compose up"),
    ("Makefile",           "make run"),
    ("manage.py",          "python3 manage.py runserver"),
    ("package.json",       None),   # inspected further below
    ("Cargo.toml",         "cargo run"),
    ("go.mod",             "go run ."),
    ("pom.xml",            "mvn spring-boot:run"),
    ("requirements.txt",   None),   # inspected further below
    ("main.py",            "python3 main.py"),
    ("app.py",             "python3 app.py"),
]


def _find_project(name: str) -> Path | None:
    """Case-insensitive search for a folder matching `name` under common
    dev roots, then falls back to a shallow scan of the whole home dir."""
    name_lower = name.strip().lower()
    home = Path.home()

    # exact path given?
    direct = Path(name).expanduser()
    if direct.is_dir():
        return direct

    candidates = []
    for root_name in _SEARCH_ROOTS:
        root = home / root_name
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and name_lower in child.name.lower():
                candidates.append(child)

    if candidates:
        # prefer exact (case-insensitive) name match over a substring match
        exact = [c for c in candidates if c.name.lower() == name_lower]
        return (exact or candidates)[0]

    # last resort: shallow scan of home (depth 2) for a matching dir name
    try:
        for child in home.glob("*/*"):
            if child.is_dir() and child.name.lower() == name_lower:
                return child
    except Exception:
        pass

    return None


def _detect_run_command(project_dir: Path) -> str | None:
    for marker, cmd in _PROJECT_MARKERS:
        marker_path = project_dir / marker

        if not marker_path.exists():
            continue

        if marker == "package.json":
            try:
                import json
                pkg = json.loads(marker_path.read_text(encoding="utf-8"))
                scripts = pkg.get("scripts", {})
                for script_name in ("dev", "start"):
                    if script_name in scripts:
                        return f"npm run {script_name}"
            except Exception:
                pass
            return "npm start"

        if marker == "requirements.txt":
            for entry_name in ("main.py", "app.py", "run.py", "server.py"):
                if (project_dir / entry_name).exists():
                    return f"python3 {entry_name}"
            continue  # no obvious entry point, keep checking other markers

        if cmd:
            return cmd

    return None


def _open_terminal_with_command(project_dir: Path, cmd: str) -> str:
    system = platform.system()
    full_cmd = f'cd "{project_dir}" && {cmd}'

    if system == "Windows":
        subprocess.Popen(f'start cmd /k "{full_cmd}"', shell=True)
        return "Opened a terminal window and started the project."

    if system == "Darwin":
        escaped = full_cmd.replace('"', '\\"')
        subprocess.Popen([
            "osascript", "-e",
            f'tell application "Terminal" to do script "{escaped}"'
        ])
        return "Opened a terminal window and started the project."

    # Linux — prefer kitty (the user's terminal). When running inside an
    # existing kitty session, open a split window via remote control so the
    # project runs right next to Lessan; otherwise open a standalone kitty
    # window. Fall back to other terminal emulators if kitty is unavailable.
    # The command shows its output and exit code for a few seconds, then the
    # window closes on its own — no keypress or "close?" prompt needed.
    import os
    wrapped = (
        f'{full_cmd}; ec=$?; echo; echo "Exit code: $ec"; '
        f'sleep 3; exit $ec'
    )

    if shutil.which("kitty"):
        if kitty_launch_split(["bash", "-c", wrapped])[0]:
            return "Opened a kitty split window and started the project."
        # No --hold: kitty closes the window automatically when the shell exits.
        subprocess.Popen(["kitty", "bash", "-c", wrapped])
        return "Opened a kitty window and started the project."

    for terminal_cmd in (
        ["gnome-terminal", "--", "bash", "-c", wrapped],
        ["konsole", "-e", "bash", "-c", wrapped],
        ["xterm", "-e", "bash", "-c", wrapped],
    ):
        try:
            subprocess.Popen(terminal_cmd)
            return "Opened a terminal window and started the project."
        except FileNotFoundError:
            continue
    return "No terminal emulator found (tried kitty, gnome-terminal, konsole, xterm)."


def run_project(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    name = (parameters or {}).get("name", "").strip()
    if not name:
        return "Which project would you like me to run, sir?"

    project_dir = _find_project(name)
    if not project_dir:
        return (
            f"I couldn't find a project called '{name}' in your usual "
            f"project folders. If it's somewhere unusual, give me the full path."
        )

    cmd = _detect_run_command(project_dir)
    if not cmd:
        return (
            f"Found '{project_dir}', but I couldn't tell how to run it — "
            f"no package.json, Makefile, main.py, or similar marker file found."
        )

    if player:
        player.write_log(f"[project_launcher] {project_dir} -> {cmd}")
    print(f"[project_launcher] 🚀 {project_dir} -> {cmd}")

    return _open_terminal_with_command(project_dir, cmd)
