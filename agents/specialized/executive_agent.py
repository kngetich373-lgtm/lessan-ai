"""ExecutiveAgent — orchestration and delegation of tasks to other agents."""

from typing import Any, Dict

from agents.framework.base_agent import BaseAgent, AgentTask
from agents.framework.agent_registry import agent_registry


@agent_registry.register
class ExecutiveAgent(BaseAgent):
    """Coordinates other agents and makes high-level decisions."""

    name = "executive"
    display_name = "Executive"
    description = "Orchestrates other agents, plans work and delegates tasks."
    icon = "👑"
    color = "#fbbf24"

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_capability(
            "delegate",
            "Delegate a task to another agent",
            self._cap_delegate,
            {"agent": {"type": "string"}, "task": {"type": "string"}},
        )
        self.register_capability(
            "plan",
            "Break a goal into a plan of delegate-able steps",
            self._cap_plan,
            {"goal": {"type": "string"}},
        )

    def _cap_delegate(self, agent: str, task: str) -> str:
        from agents.framework.agent_manager import agent_manager

        try:
            result = agent_manager.dispatch(agent, task)
            return f"Delegated to {agent}: {result}"
        except Exception as exc:
            raise RuntimeError(f"Delegation to {agent} failed: {exc}") from exc

    def _cap_plan(self, goal: str) -> str:
        from agent.planner import plan_tasks

        try:
            plan = plan_tasks(goal)
            return plan if isinstance(plan, str) else str(plan)
        except Exception:
            steps = self._simple_plan(goal)
            return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))

    @staticmethod
    def _simple_plan(goal: str) -> list[str]:
        return [
            f"Analyze requirements for: {goal}",
            "Develop a detailed implementation plan",
            "Delegate implementation to the engineering agent",
            "Review the results and iterate",
            "Deliver the final outcome",
        ]

    def on_run(self, task: AgentTask) -> Any:
        return self._cap_plan(task.description)