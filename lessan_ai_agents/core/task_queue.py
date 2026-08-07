"""
Task Queue.

Holds units of work to be handed to agents. Deliberately unaware of
*how* a task gets executed (no agent references, no orchestration
logic) — AgentManager pulls tasks off the queue and dispatches them.
This keeps the queue reusable for any future scheduling strategy.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum, unique
from itertools import count
from typing import Optional, Protocol, runtime_checkable
from uuid import uuid4


@unique
class TaskPriority(IntEnum):
    """Lower value = higher priority, so it sorts naturally in a heap."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@unique
class TaskState(Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A unit of work destined for a named agent (or an agent role)."""

    title: str
    target_agent: str
    payload: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    task_id: str = field(default_factory=lambda: str(uuid4()))
    state: TaskState = TaskState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class ITaskQueue(Protocol):
    """Queue contract: enqueue, priority-ordered dequeue, and status
    queries. No knowledge of agents' internals required."""

    def enqueue(self, task: Task) -> None: ...

    def dequeue(self) -> Optional[Task]: ...

    def peek(self) -> Optional[Task]: ...

    def cancel(self, task_id: str) -> bool: ...

    def size(self) -> int: ...


class InMemoryTaskQueue:
    """Default, dependency-free priority queue implementation of
    ITaskQueue. FIFO within the same priority level.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, Task]] = []
        self._counter = count()  # tie-breaker to preserve FIFO order
        self._cancelled_ids: set[str] = set()

    def enqueue(self, task: Task) -> None:
        heapq.heappush(self._heap, (task.priority.value, next(self._counter), task))

    def dequeue(self) -> Optional[Task]:
        while self._heap:
            _, _, task = heapq.heappop(self._heap)
            if task.task_id in self._cancelled_ids:
                continue
            task.state = TaskState.DISPATCHED
            return task
        return None

    def peek(self) -> Optional[Task]:
        for _, _, task in sorted(self._heap):
            if task.task_id not in self._cancelled_ids:
                return task
        return None

    def cancel(self, task_id: str) -> bool:
        self._cancelled_ids.add(task_id)
        return True

    def size(self) -> int:
        return len(
            [t for _, _, t in self._heap if t.task_id not in self._cancelled_ids]
        )
