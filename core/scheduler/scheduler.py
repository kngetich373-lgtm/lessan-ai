"""Task scheduler for Lessan AI."""

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


@dataclass
class Task:
    """Represents a schedulable unit of work."""

    name: str
    func: Callable[[], Any]
    priority: TaskPriority = TaskPriority.NORMAL
    run_at: Optional[datetime] = None
    interval_seconds: Optional[float] = None
    max_runs: Optional[int] = None
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    run_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None

    @property
    def is_due(self) -> bool:
        if self.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            return False
        if self.max_runs is not None and self.run_count >= self.max_runs:
            return False
        if self.run_at is not None:
            return datetime.now() >= self.run_at
        # Interval tasks with no run_at are controlled by next_run
        return True

    @property
    def next_run(self) -> Optional[datetime]:
        if self.interval_seconds is None:
            return self.run_at
        base = self.last_run or self.run_at or datetime.now()
        return base + timedelta(seconds=self.interval_seconds)

    @property
    def should_run(self) -> bool:
        if not self.is_due:
            return False
        if self.interval_seconds is None:
            # One-shot task: only run once, when the scheduled time passes
            if self.run_count > 0:
                return False
            return True
        # Interval task
        if self.status == TaskStatus.SCHEDULED:
            return datetime.now() >= (self.next_run or datetime.now())
        return True


class Scheduler:
    """Runs tasks in a background worker thread.

    Supports:
      - One-shot tasks (run once at a time or immediately).
      - Recurring interval tasks.
      - Priority ordering.
    """

    def __init__(self) -> None:
        self._queue: "queue.PriorityQueue" = queue.PriorityQueue()
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def start(self) -> "Scheduler":
        """Start the worker thread."""
        with self._lock:
            if self._started:
                return self
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop, name="lessan-scheduler", daemon=True
            )
            self._thread.start()
            self._started = True
        return self

    def stop(self, cancel_pending: bool = True) -> None:
        """Stop the worker thread."""
        self._stop_event.set()
        if cancel_pending:
            with self._lock:
                for task in self._tasks.values():
                    if task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                        task.status = TaskStatus.CANCELLED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._started = False

    def add(self, task: Task) -> str:
        """Add a task. Returns its task ID."""
        with self._lock:
            self._tasks[task.task_id] = task
        self._queue.put((task.priority.value, datetime.now().timestamp(), task))
        return task.task_id

    def add_task(
        self,
        name: str,
        func: Callable[[], Any],
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        run_at: Optional[datetime] = None,
        interval_seconds: Optional[float] = None,
        max_runs: Optional[int] = None,
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create and add a task in one call."""
        task = Task(
            name=name,
            func=func,
            priority=priority,
            run_at=run_at,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            args=args,
            kwargs=kwargs or {},
        )
        return self.add(task)

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task. Returns True if cancelled."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                task.status = TaskStatus.CANCELLED
                return True
            return False

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def clear_finished(self) -> int:
        """Remove completed/failed/cancelled tasks. Returns count removed."""
        with self._lock:
            finished = [
                t
                for t in self._tasks.values()
                if t.status
                in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            for t in finished:
                del self._tasks[t.task_id]
            return len(finished)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                _, _, task = self._queue.get(timeout=1.0)
            except queue.Empty:
                # Check for deferred tasks
                self._dispatch_due()
                continue

            if task.status == TaskStatus.CANCELLED:
                continue

            now = datetime.now()
            if task.run_at is not None and now < task.run_at:
                # Not due yet — put it back and check later
                self._queue.put((task.priority.value, task.run_at.timestamp(), task))
                time.sleep(0.25)
                continue

            self._execute(task)

            # Recurring task — re-queue
            if task.interval_seconds is not None and task.status == TaskStatus.COMPLETED:
                if task.max_runs is None or task.run_count < task.max_runs:
                    self._queue.put(
                        (
                            task.priority.value,
                            (datetime.now() + timedelta(seconds=task.interval_seconds)).timestamp(),
                            task,
                        )
                    )

    def _dispatch_due(self) -> None:
        """Process tasks whose scheduled time has arrived."""
        with self._lock:
            tasks = [
                t
                for t in self._tasks.values()
                if t.should_run and t.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED)
            ]
        for task in tasks:
            self._execute(task)
            if task.interval_seconds is not None and task.status == TaskStatus.COMPLETED:
                if task.max_runs is None or task.run_count < task.max_runs:
                    task.status = TaskStatus.SCHEDULED
                    task.last_run = datetime.now()

    def _execute(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now()
        try:
            task.result = task.func(*task.args, **task.kwargs)
            task.status = TaskStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001
            task.error = str(exc)
            task.status = TaskStatus.FAILED
        task.run_count += 1
        print(
            f"[Scheduler] {'✅' if task.status == TaskStatus.COMPLETED else '❌'} "
            f"{task.name} ({task.task_id})"
        )


# Global scheduler instance
scheduler = Scheduler()