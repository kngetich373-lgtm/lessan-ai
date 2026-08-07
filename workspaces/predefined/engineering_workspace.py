"""Engineering workspace for software development workflows."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class EngineeringWorkspace(BaseWorkspace):
    """Software engineering workspace with development tools."""

    name = "engineering"
    display_name = "Engineering"
    description = "Plan, build, debug and deploy software projects."
    icon = "⚙️"
    color = "#22d3ee"
    order = 20

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.set_session("project_root", config.get("project_root", str(Path.home())))

        self.register_tool(
            "list_projects",
            "List engineering projects in the workspace root",
            self._tool_list_projects,
        )
        self.register_tool(
            "open_project",
            "Open a project in the default editor",
            self._tool_open_project,
            {"name": {"type": "string", "description": "Project folder name"}},
        )
        self.register_tool(
            "run_build",
            "Run a build command in the active project",
            self._tool_run_build,
            {"command": {"type": "string", "description": "Build command (e.g. npm run build)"}},
        )
        self.register_tool(
            "git_status",
            "Show git status of the active project",
            self._tool_git_status,
        )

    # ------------------------------------------------------------------ #
    # Tools
    # ------------------------------------------------------------------ #
    def _project_root(self) -> Path:
        root = self.get_session("project_root", str(Path.home()))
        return Path(root)

    def _tool_list_projects(self) -> str:
        root = self._project_root()
        if not root.exists():
            return f"Project root '{root}' does not exist."
        projects = []
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                if (entry / ".git").exists() or (entry / "package.json").exists() \
                        or (entry / "pyproject.toml").exists() or (entry / "Cargo.toml").exists():
                    projects.append(entry.name)
        if not projects:
            return f"No recognizable projects found in {root}."
        return "Projects:\n" + "\n".join(f"  - {p}" for p in projects[:30])

    def _tool_open_project(self, name: str) -> str:
        root = self._project_root() / name
        if not root.exists():
            return f"Project '{name}' not found in {self._project_root()}."
        try:
            import subprocess
            subprocess.Popen(["code", str(root)])  # VS Code
            self.set_session("active_project", name)
            return f"Opened project '{name}' in VS Code."
        except Exception as exc:
            return f"Could not open project: {exc}"

    def _tool_run_build(self, command: str) -> str:
        project = self.get_session("active_project")
        if not project:
            return "No active project. Open one first with 'open_project'."
        import subprocess
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=120,
                cwd=str(self._project_root() / project),
            )
            if result.returncode == 0:
                return f"Build succeeded:\n{result.stdout[:800]}"
            return f"Build failed ({result.returncode}):\n{result.stderr[:800] or result.stdout[:800]}"
        except subprocess.TimeoutExpired:
            return "Build timed out after 120 seconds."

    def _tool_git_status(self) -> str:
        project = self.get_session("active_project")
        import subprocess
        cwd = str(self._project_root() / project) if project else str(self._project_root())
        try:
            result = subprocess.run(
                ["git", "status", "--short"], capture_output=True, text=True, cwd=cwd,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "Working tree clean."
            return f"Git error: {result.stderr[:300]}"
        except Exception as exc:
            return f"Could not run git: {exc}"