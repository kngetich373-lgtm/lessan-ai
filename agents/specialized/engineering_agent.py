"""EngineeringAgent — software development tasks."""

from typing import Any, Dict

from agents.framework.base_agent import BaseAgent, AgentTask
from agents.framework.agent_registry import agent_registry


@agent_registry.register
class EngineeringAgent(BaseAgent):
    """Plans, writes, and validates software engineering work."""

    name = "engineering"
    display_name = "Engineering"
    description = "Build, test, debug and deploy software."
    icon = "⚙️"
    color = "#22d3ee"

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_capability(
            "analyze_requirements",
            "Analyze project requirements",
            self._cap_analyze,
            {"requirements": {"type": "string"}},
        )
        self.register_capability(
            "find_files",
            "Find matching source files in a project",
            self._cap_find_files,
            {"pattern": {"type": "string"}, "root": {"type": "string"}},
        )
        self.register_capability(
            "run_command",
            "Run a shell command in the project",
            self._cap_run_command,
            {"command": {"type": "string"}, "cwd": {"type": "string"}},
        )

    def _cap_analyze(self, requirements: str) -> str:
        return (
            f"Requirements analysis:\n\n"
            f"Input: {requirements}\n\n"
            "1. Functional requirements: to be extracted from the input.\n"
            "2. Non-functional requirements: performance, security, usability.\n"
            "3. Constraints: platforms, legacy systems, dependencies.\n"
            "4. Success criteria: measurable outcomes.\n"
        )

    def _cap_find_files(self, pattern: str, root: str = ".") -> str:
        import os
        import re

        regex = re.compile(pattern)
        matches = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith((".git", "node_modules", "venv", "__pycache__"))]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                if regex.search(fname):
                    matches.append(full)
                if len(matches) >= 100:
                    break
            if len(matches) >= 100:
                break
        if not matches:
            return f"No files matched pattern '{pattern}' under {root}."
        return "Matching files:\n" + "\n".join(matches[:50])

    def _cap_run_command(self, command: str, cwd: str = ".") -> str:
        import subprocess

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "Command completed."
            return f"Failed ({result.returncode}): {result.stderr.strip()[:600]}"
        except subprocess.TimeoutExpired:
            return "Command timed out."

    def on_run(self, task: AgentTask) -> Any:
        description = task.description
        if description.startswith("analyze"):
            return self._cap_analyze(description)
        return f"Engineering agent received task: {description}"