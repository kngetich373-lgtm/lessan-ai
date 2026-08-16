"""SystemOrchestrator - central coordinator of Lessan AI."""

import traceback
from typing import Any, Dict, Optional

from core.event_bus import event_bus
from core.logging import get_logger
from core.state import state as state_store

from core.orchestrator.interfaces import (
    AgentSelector, MemoryStore, ModelRouter, UIStateNotifier,
    WorkflowSelector, WorkspaceSelector,
)
from core.orchestrator.models import OrchestrationResult, UserRequest

logger = get_logger("SystemOrchestrator")

EV_REQUEST_RECEIVED = "orchestrator.request_received"
EV_WORKSPACE_SELECTED = "orchestrator.workspace_selected"
EV_WORKFLOW_SELECTED = "orchestrator.workflow_selected"
EV_AGENT_SELECTED = "orchestrator.agent_selected"
EV_PROCESSING_STARTED = "orchestrator.processing_started"
EV_AGENT_RESPONSE = "orchestrator.agent_response"
EV_MEMORY_UPDATED = "orchestrator.memory_updated"
EV_REQUEST_COMPLETED = "orchestrator.request_completed"
EV_REQUEST_FAILED = "orchestrator.request_failed"


class SystemOrchestrator:
    """Coordinates request processing across all Lessan AI subsystems.

    Dependencies are injected through interfaces so the orchestrator remains
    independent from concrete model, agent, workflow, memory, and UI
    implementations.
    """

    def __init__(self, model_router: ModelRouter,
                 workspace_selector: WorkspaceSelector,
                 workflow_selector: WorkflowSelector,
                 agent_selector: AgentSelector,
                 memory_store: MemoryStore,
                 ui_notifier: UIStateNotifier,
                 workflow_engine: Any = None,
                 agent_manager: Any = None,
                 workspace_manager: Any = None,
                 event_bus_instance: Any = None):
        self._model_router = model_router
        self._workspace_selector = workspace_selector
        self._workflow_selector = workflow_selector
        self._agent_selector = agent_selector
        self._memory_store = memory_store
        self._ui_notifier = ui_notifier
        self._workflow_engine = workflow_engine
        self._agent_manager = agent_manager
        self._workspace_manager = workspace_manager
        self._event_bus = event_bus_instance or event_bus

    def handle(self, request: UserRequest) -> OrchestrationResult:
        """Process one incoming request synchronously and return its result."""
        result = OrchestrationResult(request)
        self._publish(EV_REQUEST_RECEIVED, _req_payload(request, result))
        self._notify_ui("PROCESSING", {"request_id": str(request.id)})

        try:
            workspace = self._select_workspace(request, result)
            workflow = self._select_workflow(request, workspace, result)
            agent = self._select_agent(request, workspace, result)

            self._notify_ui("EXECUTING", {"request_id": str(request.id)})
            self._publish(EV_PROCESSING_STARTED, _req_payload(request, result))

            if workflow and self._workflow_engine:
                output = self._run_workflow(request, workflow, result)
            elif agent and self._agent_manager:
                output = self._run_agent(request, agent, result)
            else:
                output = self._run_direct(request, workspace, agent)

            result.complete(output)
            self._update_memory(request.text, str(output))
            self._publish(EV_REQUEST_COMPLETED, _req_payload(request, result))
            self._notify_ui("IDLE", {"request_id": str(request.id), "success": True})
            return result

        except Exception as exc:
            result.fail(f"{type(exc).__name__}: {exc}")
            self._publish(EV_REQUEST_FAILED, _req_payload(request, result))
            logger.error(f"Request {request.id} failed: {exc}\n{traceback.format_exc()}")
            self._notify_ui("ERROR", {"request_id": str(request.id), "error": result.error})
            return result

    def submit(self, request: UserRequest, background: bool = False) -> OrchestrationResult:
        """Submit a request synchronously or to the shared background scheduler.

        The returned result object is updated in place when a background task
        finishes, allowing callers to retain a stable request/result handle.
        """
        if not background:
            return self.handle(request)

        from core.scheduler import scheduler

        result = OrchestrationResult(request)

        def run() -> None:
            completed = self.handle(request)
            result.success = completed.success
            result.output = completed.output
            result.error = completed.error
            result.workspace = completed.workspace
            result.workflow = completed.workflow
            result.agent = completed.agent
            result.started_at = completed.started_at
            result.completed_at = completed.completed_at

        scheduler.start()
        scheduler.add_task(
            name=f"orchestrate:{request.id}",
            func=run,
        )
        return result

    def _select_workspace(self, request, result):
        self._notify_ui("THINKING", {"request_id": str(request.id)})
        workspace = request.workspace_hint or self._workspace_selector.select(request)
        if workspace not in self._workspace_selector.available_workspaces():
            raise ValueError(f"Workspace '{workspace}' is not registered.")
        result.workspace = workspace
        state_store.set("orchestrator.active_workspace", workspace)
        self._publish(EV_WORKSPACE_SELECTED, _req_payload(request, result))
        return workspace

    def _select_workflow(self, request, workspace, result):
        workflow = request.workflow_hint or self._workflow_selector.select(request, workspace)
        if workflow is not None and workflow not in self._workflow_selector.available_workflows():
            raise ValueError(f"Workflow '{workflow}' is not registered.")
        result.workflow = workflow
        if workflow:
            self._publish(EV_WORKFLOW_SELECTED, _req_payload(request, result))
        return workflow

    def _select_agent(self, request, workspace, result):
        agent = self._agent_selector.select(request, workspace)
        if agent is not None and agent not in self._agent_selector.available_agents():
            raise ValueError(f"Agent '{agent}' is not registered.")
        result.agent = agent
        if agent:
            state_store.set("orchestrator.active_agent", agent)
            self._publish(EV_AGENT_SELECTED, _req_payload(request, result))
        return agent

    def _run_workflow(self, request, workflow, result):
        self._publish("orchestrator.workflow_started", _req_payload(request, result))
        exec_result = self._workflow_engine.execute(workflow, context=request.context)
        self._record_history(exec_result)
        self._publish("orchestrator.workflow_completed", _req_payload(request, result))
        return _format_workflow_output(exec_result, workflow)

    def _run_agent(self, request, agent, result):
        response = self._agent_manager.dispatch(agent, request.text, context=request.context)
        self._publish(EV_AGENT_RESPONSE, {**_req_payload(request, result), "output": str(response)})
        return str(response)

    def _run_direct(self, request, workspace, agent):
        if not self._model_router.is_available():
            raise RuntimeError("No AI model route is available.")
        memory_block = self._memory_store.format_for_prompt(self._memory_store.load())
        system = f"Active workspace: {workspace}."
        if agent:
            system += f" Preferred agent: {agent}."
        if memory_block:
            system += f"\n\n{memory_block}"
        return self._model_router.complete(request.text, system=system)

    def _update_memory(self, source: str, target: str) -> None:
        # MemoryStore.save() is intended for factual updates. A normal response
        # is not automatically treated as a durable fact, preventing accidental
        # long-term memory pollution. Memory-specific subsystems may explicitly
        # persist facts when appropriate.
        self._publish(EV_MEMORY_UPDATED, {
            "source": source,
            "target": target,
            "keys": [],
            "persisted": False,
        })

    def _record_history(self, exec_result: Any) -> None:
        if self._workflow_engine is None:
            return
        history = getattr(self._workflow_engine, "history", None)
        if history is None:
            return
        try:
            status = getattr(exec_result, "status", None)
            if status is None:
                return
            if status in ("completed", "succeeded", "success"):
                history.record_completion(exec_result)
            elif status in ("failed", "error"):
                history.record_error(
                    exec_result,
                    getattr(exec_result, "error", None) or "workflow failed",
                )
        except Exception:
            logger.warning("Workflow history recording failed", exc_info=True)

    def _notify_ui(self, state_name: str, payload: Dict[str, Any]) -> None:
        try:
            self._ui_notifier.notify(state_name, payload)
        except Exception as exc:
            logger.warning(f"UI notify failed: {exc}")

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event, payload)
        except Exception as exc:
            logger.warning(f"Event '{event}' publish failed: {exc}")


def _req_payload(request: UserRequest, result: OrchestrationResult) -> Dict[str, Any]:
    return {
        "request_id": str(request.id),
        "source": request.source,
        "text": request.text,
        "session_id": request.session_id,
        "workspace": result.workspace,
        "workflow": result.workflow,
        "agent": result.agent,
        "success": result.success,
        "error": result.error,
        "output": result.output,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
    }


def _format_workflow_output(exec_result: Any, workflow: str) -> str:
    if exec_result is None:
        return f"Workflow '{workflow}' completed."
    for attr in ("output", "result"):
        try:
            val = getattr(exec_result, attr, None)
            if val:
                return str(val)
        except Exception:
            pass
    try:
        if getattr(exec_result, "status", None):
            return f"Workflow '{workflow}' finished with status {exec_result.status}."
    except Exception:
        pass
    return f"Workflow '{workflow}' completed."
