"""
AgentManager.

The one class that is allowed to know about the registry, the task
queue, and the communication bus at the same time — everything else in
the framework talks to at most one of them. AgentManager's job is
strictly dispatch: pull a Task, find its target agent via the
registry, hand it an AgentContext, collect the AgentResult, and
publish a STATUS_UPDATE on the bus. It does not decide *what* work
exists (that's the caller enqueuing tasks) and does not implement any
particular multi-agent workflow (per project scope: "do not implement
workflows").
"""

from __future__ import annotations

from typing import Optional

from .agent_registry import IAgentRegistry
from .base_agent import AgentContext, AgentResult
from .communication import AgentMessage, IAgentCommunicationBus, MessageType
from .task_queue import ITaskQueue, Task, TaskState


class AgentManager:
    """Coordinates task dispatch across registered agents.

    All three collaborators are injected (Dependency Inversion) so
    tests can swap in fakes, and so a future distributed deployment
    can supply alternative queue/bus implementations without touching
    this class.
    """

    def __init__(
        self,
        registry: IAgentRegistry,
        task_queue: ITaskQueue,
        communication_bus: Optional[IAgentCommunicationBus] = None,
    ) -> None:
        self.registry = registry
        self.task_queue = task_queue
        self.communication_bus = communication_bus

    def submit(self, task: Task) -> None:
        """Enqueue a task for later dispatch."""
        self.task_queue.enqueue(task)

    def dispatch_next(self) -> Optional[AgentResult]:
        """Pop the highest-priority pending task and run it against its
        target agent. Returns None if the queue is empty or the target
        agent isn't registered (the task is dropped in that case —
        callers wanting retry/dead-letter semantics build that on top,
        since this framework intentionally stops at dispatch)."""
        task = self.task_queue.dequeue()
        if task is None:
            return None

        agent = self.registry.get(task.target_agent)
        if agent is None:
            task.state = TaskState.CANCELLED
            self._publish_status(task, success=False, detail="agent_not_found")
            return None

        context = AgentContext(task_id=task.task_id, payload=task.payload)
        result = agent.execute(context)
        task.state = TaskState.DONE
        self._publish_status(task, success=result.success, detail=result.error)
        return result

    def drain(self, max_tasks: Optional[int] = None) -> list[AgentResult]:
        """Dispatch tasks until the queue is empty or `max_tasks` is
        reached. Convenience wrapper around `dispatch_next` — still no
        workflow logic, just repetition."""
        results: list[AgentResult] = []
        dispatched = 0
        while self.task_queue.size() > 0:
            if max_tasks is not None and dispatched >= max_tasks:
                break
            result = self.dispatch_next()
            dispatched += 1
            if result is not None:
                results.append(result)
        return results

    def _publish_status(self, task: Task, success: bool, detail: Optional[str]) -> None:
        if self.communication_bus is None:
            return
        self.communication_bus.publish(
            AgentMessage(
                sender="AgentManager",
                message_type=MessageType.STATUS_UPDATE,
                payload={
                    "task_id": task.task_id,
                    "target_agent": task.target_agent,
                    "success": success,
                    "detail": detail,
                },
            )
        )
