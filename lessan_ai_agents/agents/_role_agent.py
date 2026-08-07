"""
RoleAgent — shared scaffolding for every concrete role agent.

Not one of the eleven named agents itself; it exists so CEO Agent,
Product Manager, etc. don't each re-implement identical
describe()/build_prompt()/_run() boilerplate (DRY, and it keeps each
concrete agent file focused on *what makes that role different*:
its responsibilities, objectives, capabilities, and prompt template).

Per project scope, `_run` is inert by default — it returns a structured
"role response" describing what the agent would do with the given
context, so the surrounding architecture (queue, manager, bus, memory)
is fully exercised without this layer overstepping into
implementation. An execution backend can be injected via the optional
``executor`` (callable ``prompt -> str``); when one is present, `_run`
sends the rendered prompt to it and returns its output, turning the
agent into a real LLM-driven worker without RoleAgent knowing anything
about the backend.
"""

from __future__ import annotations

from typing import Any, Callable

from lessan_ai_agents.core.base_agent import (
    AgentCapability,
    AgentContext,
    BaseAgent,
    PromptTemplate,
)
from lessan_ai_agents.core.memory import IAgentMemory
from lessan_ai_agents.core.communication import IAgentCommunicationBus


class RoleAgent(BaseAgent):
    """Common implementation shared by all concrete role agents."""

    def __init__(
        self,
        name: str,
        role: str,
        responsibilities: list[str],
        objectives: list[str],
        capabilities: list[AgentCapability],
        prompt_template: PromptTemplate,
        memory: "IAgentMemory | None" = None,
        communication_bus: "IAgentCommunicationBus | None" = None,
        executor: "Callable[[str], str] | None" = None,
    ) -> None:
        super().__init__(
            name=name,
            role=role,
            responsibilities=responsibilities,
            objectives=objectives,
            capabilities=capabilities,
            prompt_template=prompt_template,
            memory=memory,
            communication_bus=communication_bus,
        )
        self.executor = executor

    def describe(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "responsibilities": self.responsibilities,
            "objectives": self.objectives,
            "capabilities": [
                {"name": c.name, "description": c.description}
                for c in self.capabilities
            ],
            "status": self.status.value,
        }

    def build_prompt(self, context: AgentContext) -> str:
        variables = {var: context.payload.get(var, "") for var in self.prompt_template.variables}
        return self.prompt_template.render(**variables)

    def _run(self, context: AgentContext) -> Any:
        # A custom prompt in the payload lets an orchestrator override
        # the agent's static template with task-specific instructions
        # (e.g. a JSON file-plan request or a code-generation prompt)
        # while still routing through this agent's identity and the
        # framework's queue/manager/memory.
        prompt = context.payload.get("prompt") or self.build_prompt(context)
        if self.memory is not None:
            self.memory.remember(
                key=f"{self.name}:{context.task_id}",
                value={"prompt": prompt, "payload": context.payload},
                tags=(self.role,),
            )
        if self.executor is not None:
            return {
                "agent": self.name,
                "role": self.role,
                "task_id": context.task_id,
                "prompt": prompt,
                "output": self.executor(prompt),
                "note": "Executed via injected LLM executor.",
            }
        # Architecture-only response envelope, preserved when no
        # executor is wired so the framework stays inert and
        # dependency-free on its own.
        return {
            "agent": self.name,
            "role": self.role,
            "task_id": context.task_id,
            "prompt": prompt,
            "note": "Architecture stub: no software generation performed.",
        }
