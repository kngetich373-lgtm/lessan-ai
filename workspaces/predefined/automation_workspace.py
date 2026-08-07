"""Automation workspace for workflow automation."""

from typing import Any, Dict

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class AutomationWorkspace(BaseWorkspace):
    """Computer, browser, terminal, and file automation."""

    name = "automation"
    display_name = "Automation"
    description = "Automate computer control, browser actions, terminal commands and file workflows."
    icon = "🤖"
    color = "#ffd166"
    order = 50

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_tool("run_command", "Run a terminal command", self._tool_run_command,
                           {"command": {"type": "string", "description": "Command to run"}})
        self.register_tool("take_screenshot", "Capture the screen", self._tool_screenshot)

    def _tool_run_command(self, command: str) -> str:
        import subprocess
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return result.stdout.strip() or "Command completed."
            return f"Failed: {result.stderr.strip()[:400]}"
        except subprocess.TimeoutExpired:
            return "Command timed out."

    def _tool_screenshot(self) -> str:
        try:
            import pyautogui
            path = "reports/screenshots/auto_capture.png"
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pyautogui.screenshot(path)
            return f"Screenshot saved to {path}"
        except Exception as exc:
            return f"Screenshot failed: {exc}"