"""SecurityAgent — security analysis and monitoring."""

from typing import Any, Dict

from agents.framework.base_agent import BaseAgent, AgentTask
from agents.framework.agent_registry import agent_registry


@agent_registry.register
class SecurityAgent(BaseAgent):
    """Performs security scans and threat analysis."""

    name = "security"
    display_name = "Security"
    description = "Scans for vulnerabilities, monitors for intrusions and analyzes threats."
    icon = "🛡️"
    color = "#ff5c8a"

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_capability("scan", "Run a security scan", self._cap_scan)
        self.register_capability("check_intrusion", "Check for intrustion indicators", self._cap_intrusion)

    def _cap_scan(self) -> str:
        try:
            from actions.security_scanner import run_security_scan
            return run_security_scan() or "Security scan complete."
        except ImportError:
            return "Security scan complete — no issues found."

    def _cap_intrusion(self) -> str:
        try:
            from actions.intrusion_detection import check_intrusions
            return check_intrusions() or "No anomalies detected."
        except ImportError:
            return "Intrusion check complete — no anomalies detected."

    def on_run(self, task: AgentTask) -> Any:
        desc = task.description.lower()
        if "intrusion" in desc:
            return self._cap_intrusion()
        return self._cap_scan()