"""AutomationAgent — workflow and system automation."""

from typing import Any, Dict

from agents.framework.base_agent import BaseAgent, AgentTask
from agents.framework.agent_registry import agent_registry


@agent_registry.register
class AutomationAgent(BaseAgent):
    """Runs commands, automates workflows and controls the system."""

    name = "automation"
    display_name = "Automation"
    description = "Automates terminal, browser, file and computer actions."
    icon = "🤖"
    color = "#ffd166"

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_capability("run_command", "Run a shell command", self._cap_run,
                                 {"command": {"type": "string"}})
        self.register_capability("open_app", "Open an application", self._cap_open,
                                 {"app": {"type": "string"}})

    def _cap_run(self, command: str) -> str:
        import subprocess
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return result.stdout.strip() or "Command completed."
            return f"Failed: {result.stderr.strip()[:500]}"
        except subprocess.TimeoutExpired:
            return "Command timed out."

    def _cap_open(self, app: str) -> str:
        import subprocess
        try:
            subprocess.Popen(["xdg-open", app])
            return f"Opened: {app}"
        except Exception as exc:
            return f"Could not open {app}: {exc}"

    def on_run(self, task: AgentTask) -> Any:
        return f"Automation agent received: {task.description}"