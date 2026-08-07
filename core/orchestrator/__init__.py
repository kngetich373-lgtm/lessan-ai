"""System Orchestrator package for Lessan AI."""

from core.orchestrator.interfaces import (
    AgentSelector, MemoryStore, ModelRouter, UIStateNotifier,
    WorkflowSelector, WorkspaceSelector,
)
from core.orchestrator.models import OrchestrationResult, UserRequest
from core.orchestrator.orchestrator import SystemOrchestrator

__all__ = [
    "SystemOrchestrator", "OrchestrationResult", "UserRequest",
    "ModelRouter", "WorkspaceSelector", "WorkflowSelector",
    "AgentSelector", "MemoryStore", "UIStateNotifier",
]


def register_orchestrator(container) -> SystemOrchestrator:
    """Register the SystemOrchestrator with a DI container.

    Resolves interfaces from the container; optional concrete subsystems
    (workflow engine, agent manager, workspace manager) are wired when
    available so no existing registration is disturbed.
    """
    container.register_factory(
        SystemOrchestrator,
        lambda c: SystemOrchestrator(
            model_router=c.resolve(ModelRouter),
            workspace_selector=c.resolve(WorkspaceSelector),
            workflow_selector=c.resolve(WorkflowSelector),
            agent_selector=c.resolve(AgentSelector),
            memory_store=c.resolve(MemoryStore),
            ui_notifier=c.resolve(UIStateNotifier),
            workflow_engine=c.try_resolve(object),
            agent_manager=c.try_resolve(object),
            workspace_manager=c.try_resolve(object),
        ),
    )
    return container.resolve(SystemOrchestrator)
