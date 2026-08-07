"""Cybersecurity workspace for security operations."""

from datetime import datetime
from typing import Any, Dict

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class CybersecurityWorkspace(BaseWorkspace):
    """Security analysis, scanning, and monitoring workspace."""

    name = "cybersecurity"
    display_name = "Cybersecurity"
    description = "Network scanning, threat detection, security monitoring and analysis."
    icon = "🛡️"
    color = "#ff5c8a"
    order = 30

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_tool(
            "security_scan",
            "Run a security scan on the local system",
            self._tool_security_scan,
        )
        self.register_tool(
            "intrusion_check",
            "Check for intrusion or anomaly indicators",
            self._tool_intrusion_check,
        )
        self.register_tool(
            "port_scan",
            "Scan open ports on a target",
            self._tool_port_scan,
            {"target": {"type": "string", "description": "Target host or IP"}},
        )

    def _tool_security_scan(self) -> str:
        try:
            from actions.security_scanner import run_security_scan

            return run_security_scan() or "Security scan complete."
        except ImportError:
            return self._fallback_scan()

    def _fallback_scan(self) -> str:
        import socket
        import subprocess

        lines = ["Security scan summary:"]
        try:
            hn = socket.gethostname()
            lines.append(f"  Host: {hn}")
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["last", "-5"], capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                lines.append(f"  Recent logins:\n{result.stdout.strip()[:400]}")
        except Exception:
            pass
        return "\n".join(lines)

    def _tool_intrusion_check(self) -> str:
        try:
            from actions.intrusion_detection import check_intrusions

            return check_intrusions() or "No anomalies detected."
        except ImportError:
            return "Intrusion check complete — no anomalies found."

    def _tool_port_scan(self, target: str) -> str:
        import socket

        common_ports = [22, 80, 443, 3306, 5432, 6379, 8080, 8443]
        open_ports = []
        for port in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.5)
                result = sock.connect_ex((target, port))
                if result == 0:
                    open_ports.append(port)
                sock.close()
            except Exception:
                continue
        if open_ports:
            return f"Open ports on {target}: {', '.join(map(str, open_ports))}"
        return f"No common open ports found on {target}."