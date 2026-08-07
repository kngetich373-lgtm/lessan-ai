"""Secure command execution for the File & Command Control System.

Three collaborating pieces live here:

* :class:`CommandRegistry` — known command definitions (binary, description,
  danger level) seeded from the security policy's default table;
* :class:`CommandHistory` — a bounded, in-memory record of executions;
* :class:`CommandExecutor` — runs commands as direct child processes with a
  working directory inside the approved workspace, a timeout, output caps and
  permission enforcement (see :class:`PermissionManager`).

Every run is reviewed by the security policy *before* the process spawns.
Always-denied commands raise :class:`PermissionDeniedError`; commands that
need explicit approval raise :class:`ConfirmationRequiredError` carrying a
token that can be approved via :meth:`PermissionManager.confirm`.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger

from automation.events import (
    EV_COMMAND_COMPLETED,
    EV_COMMAND_FAILED,
    EV_COMMAND_STARTED,
    emit_automation_event,
)
from automation.models import CommandSpec, DangerLevel, ExecutionResult, FileOperationKind
from automation.permissions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    PermissionManager,
)
from automation.security import COMMAND_DESCRIPTIONS, DEFAULT_COMMAND_LEVELS

logger = get_logger("automation.command")


class CommandRegistry:
    """Known command definitions with their danger levels."""

    def __init__(self) -> None:
        self._specs: Dict[str, CommandSpec] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        for name, level in DEFAULT_COMMAND_LEVELS.items():
            spec = CommandSpec(
                name=name,
                description=COMMAND_DESCRIPTIONS.get(name, f"Run {name}"),
                binary=name,
                danger_level=level,
            )
            self._specs[name] = spec

    def register(self, spec: CommandSpec) -> CommandSpec:
        """Register a command definition (replaces an existing one)."""
        self._specs[spec.name] = spec
        return spec

    def register_alias(self, name: str, binary: str, *, description: Optional[str] = None) -> CommandSpec:
        """Register a named alias of an existing binary."""
        base = self._specs.get(binary)
        if base is None:
            base = CommandSpec(name=binary, description=binary, binary=binary)
        spec = CommandSpec(
            name=name,
            description=description or f"Alias for {binary}",
            binary=binary,
            danger_level=base.danger_level,
        )
        self._specs[name] = spec
        return spec

    def lookup(self, name: str) -> Optional[CommandSpec]:
        return self._specs.get(name)

    @property
    def known_names(self) -> List[str]:
        return sorted(self._specs)

    def as_dict(self) -> List[Dict[str, Any]]:
        return [spec.as_dict() for spec in sorted(self._specs.values(), key=lambda s: s.name)]

class CommandHistory:
    """Bounded, in-memory record of command executions.

    Newest records are kept first; ``capacity`` bounds the list. The history
    is the source of truth for the state-store slice ``automation.commands.*``
    and for the tooling/agent surfaces.
    """

    def __init__(self, capacity: int = 200) -> None:
        self.capacity = max(1, int(capacity))
        self._records: List[ExecutionResult] = []

    def record(self, result: ExecutionResult) -> None:
        """Append an execution to the history (newest first)."""
        self._records.insert(0, result)
        if len(self._records) > self.capacity:
            self._records = self._records[: self.capacity]

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the newest executions as dictionaries."""
        return [r.as_dict() for r in self._records[: max(0, limit)]]

    def find(self, term: Optional[str] = None, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Search history by command text (case-insensitive substring)."""
        if not term:
            return self.recent(limit)
        needle = term.lower()
        matches = [r for r in self._records if needle in r.command.lower()]
        return [r.as_dict() for r in matches[: max(0, limit)]]

    def all(self) -> List[ExecutionResult]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


class CommandExecutor:
    """Runs commands safely inside the approved workspace.

    The security flow per run:

    1. resolve the working directory (defaults to ``default_cwd``);
    2. :meth:`PermissionManager.check` reviews the command string — always
       denied commands raise :class:`PermissionDeniedError`;
    3. confirmation-required commands raise :class:`ConfirmationRequiredError`
       (approve via :meth:`PermissionManager.confirm` and retry with
       ``confirm=True``);
    4. the process is spawned as a direct child in its own process group so
       the timeout can kill the whole tree.
    """

    def __init__(
        self,
        permission_manager: PermissionManager,
        *,
        event_bus: Any = None,
        state_store: Any = None,
        memory: Any = None,
        history: Optional[CommandHistory] = None,
        command_registry: Optional[CommandRegistry] = None,
        default_cwd: Any = None,
        default_timeout: float = 60.0,
        max_output_chars: int = 100_000,
    ) -> None:
        self._permissions = permission_manager
        self._event_bus = event_bus
        self._state = state_store
        self._memory = memory
        self._history = history or CommandHistory()
        self._registry = command_registry or CommandRegistry()
        if permission_manager.policy.command_registry is None:
            permission_manager.policy.command_registry = self._registry
        if default_cwd is None:
            default_cwd = permission_manager.policy.app_root
        self._default_cwd = str(Path(default_cwd).expanduser().resolve())
        self._default_timeout = max(0.1, float(default_timeout))
        self._max_output_chars = max(1024, int(max_output_chars))
        self._lock = threading.Lock()
        self._procs: set = set()

    @property
    def history(self) -> CommandHistory:
        return self._history

    @property
    def registry(self) -> CommandRegistry:
        return self._registry

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions


    def run(
        self,
        command: str,
        *,
        cwd: Any = None,
        timeout: Optional[float] = None,
        shell: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
        env: Optional[Dict[str, str]] = None,
        stream: Any = None,
    ) -> ExecutionResult:
        """Execute ``command`` and return an :class:`ExecutionResult`."""
        started = time.time()
        text = (command or "").strip()
        started_at = datetime.now().isoformat(timespec="seconds")
        result = ExecutionResult(command=text, started_at=started_at)

        if not text:
            result.returncode = -1
            result.stderr = "Empty command."
            return self._finish(result, started)

        # Parse into argv (shell mode keeps the raw string).
        try:
            argv = [text] if shell else shlex.split(text)
        except ValueError as exc:
            result.returncode = -1
            result.stderr = f"Could not parse command: {exc}"
            return self._finish(result, started)
        result.argv = list(argv)
        result.shell = shell

        workdir = Path(cwd).expanduser().resolve() if cwd else Path(self._default_cwd).resolve()
        result.cwd = str(workdir)

        decision = self._permissions.check(
            FileOperationKind.EXECUTE_COMMAND,
            source=workdir,
            cwd=workdir,
            command=text,
            shell=shell,
            actor=actor,
            workspace=workspace,
        )
        if not decision.allowed:
            if decision.requires_confirmation:
                if confirm and decision.token and self._permissions.confirm(decision.token, actor=actor):
                    logger.info(f"Command approved by confirmation: {text!r}")
                else:
                    raise ConfirmationRequiredError(decision.reason, token=decision.token, decision=decision)
            else:
                raise PermissionDeniedError(decision.reason, decision=decision)

        emit_automation_event(
            EV_COMMAND_STARTED,
            {"command": text, "argv": argv, "cwd": str(workdir), "actor": actor, "shell": shell},
            bus=self._event_bus,
        )

        full_env = {**os.environ, **(env or {})}
        timeout_secs = timeout if timeout is not None else self._default_timeout
        timed_out = False
        cancelled = False
        stdout = ""
        stderr = ""
        proc: Optional[subprocess.Popen] = None

        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                env=full_env,
                start_new_session=True,
            )
        except FileNotFoundError:
            result.returncode = 127
            result.stderr = f"Command not found: {argv[0]}"
            return self._finish(result, started)
        except PermissionError:
            result.returncode = 126
            result.stderr = f"Command is not executable: {argv[0]}"
            return self._finish(result, started)
        except OSError as exc:
            result.returncode = -1
            result.stderr = f"Could not start command: {exc}"
            return self._finish(result, started)

        with self._lock:
            self._procs.add(proc)
        try:
            try:
                stdout, stderr = proc.communicate(timeout=timeout_secs)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill(proc)
                stdout, stderr = proc.communicate()
        except KeyboardInterrupt:
            cancelled = True
            self._kill(proc)
            stdout, stderr = proc.communicate()
        finally:
            with self._lock:
                self._procs.discard(proc)

        result.returncode = proc.returncode
        result.stdout = (stdout or "")[: self._max_output_chars]
        result.stderr = (stderr or "")[: self._max_output_chars]
        result.timed_out = timed_out
        result.cancelled = cancelled

        if stream is not None:
            try:
                stream(result)
            except Exception:  # noqa: BLE001
                pass
        return self._finish(result, started)


    def run_async(
        self,
        command: str,
        *,
        cwd: Any = None,
        timeout: Optional[float] = None,
        shell: bool = False,
        actor: str = "user",
        workspace: Optional[str] = None,
        confirm: bool = False,
    ) -> Tuple[threading.Thread, "ResultHolder"]:
        """Run a command on a background thread.

        Returns ``(thread, holder)`` where ``holder.result`` is populated when
        the thread finishes.
        """
        holder: ResultHolder = ResultHolder()

        def _target() -> None:
            holder.result = self.run(
                command,
                cwd=cwd,
                timeout=timeout,
                shell=shell,
                actor=actor,
                workspace=workspace,
                confirm=confirm,
            )

        thread = threading.Thread(target=_target, name=f"command-{time.time_ns():x}", daemon=True)
        thread.start()
        return thread, holder

    def cancel(self, command_prefix: Optional[str] = None) -> int:
        """Terminate running processes (optionally matching a command prefix)."""
        killed = 0
        with self._lock:
            targets = list(self._procs)
        for proc in targets:
            if command_prefix and command_prefix not in " ".join((proc.args or [])):
                continue
            self._kill(proc)
            killed += 1
        return killed

    def stop_all(self) -> int:
        """Terminate every running process managed by this executor."""
        return self.cancel()

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        """Kill the process group (the whole tree) using SIGKILL."""
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass

    def _finish(self, result: ExecutionResult, started: float) -> ExecutionResult:
        """Finalise a result: timing, history, state, memory, events."""
        result.duration_ms = (time.time() - started) * 1000
        result.completed_at = datetime.now().isoformat(timespec="seconds")

        self._history.record(result)
        emit_automation_event(
            EV_COMMAND_FAILED if not result.success else EV_COMMAND_COMPLETED,
            result.as_dict(),
            bus=self._event_bus,
        )
        if self._state is not None:
            try:
                self._state.update("automation.last_command", result.as_dict())
                self._state.update("automation.commands.recent", self._history.recent(10))
            except Exception:  # noqa: BLE001
                pass
        if self._memory is not None:
            try:
                self._memory.store(
                    self._memory_context(result.cwd),
                    f"command:{time.time_ns():x}",
                    result.as_dict(),
                    tags=["automation", "commands"],
                )
            except Exception:  # noqa: BLE001
                pass
        return result

    def _memory_context(self, cwd: str):
        try:
            from memory import MemoryContext, MemoryScope

            workspace = "default"
            profile = self._permissions.policy.workspace_for(cwd) if cwd else None
            if profile is not None:
                workspace = profile.name
            return MemoryContext(scope=MemoryScope.WORKSPACE, scope_id=workspace)
        except Exception:  # noqa: BLE001
            return None


class ResultHolder:
    """Simple container for the result of an async command run."""

    def __init__(self) -> None:
        self.result: Optional[ExecutionResult] = None

