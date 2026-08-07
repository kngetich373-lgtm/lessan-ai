"""Permission enforcement for the File & Command Control System.

The :class:`PermissionManager` turns every file/command operation into a
:class:`PermissionDecision` using the :class:`SecurityPolicy`:

1. **system-critical paths** are denied outright (``/etc``, ``~/.ssh``, ...);
2. **path containment** — every source/destination must live inside an
   approved workspace root (or an explicit allowlist entry);
3. **protected paths** — destructive operations on ``.git``, ``config``,
   ``core``, ``main.py``, ... are denied outright;
4. **danger escalation** — high/critical operations and anything issued by
   an agent require an explicit, expiring *confirmation token*.

The confirmation flow is tiny: :meth:`check` returns a decision carrying a
token, and :meth:`confirm` approves it. Denials and confirmations are
published on the event bus, mirrored to the state store and (optionally)
recorded in memory.
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from automation.events import (
    EV_PERMISSION_CHECKED,
    EV_PERMISSION_CONFIRMED,
    EV_PERMISSION_DENIED,
    emit_automation_event,
)
from automation.models import (
    DESTRUCTIVE_KINDS,
    KIND_DANGER,
    DangerLevel,
    FileOperationKind,
    PermissionDecision,
    WorkspaceProfile,
)
from automation.security import SecurityPolicy

logger = get_logger("automation.permissions")


class PermissionDeniedError(Exception):
    """Raised when an operation is not allowed by the security policy."""

    def __init__(self, message: str, decision: Optional[PermissionDecision] = None) -> None:
        super().__init__(message)
        self.decision = decision


class ConfirmationRequiredError(Exception):
    """Raised when an operation needs explicit user confirmation.

    The :attr:`token` can be passed back to :meth:`PermissionManager.confirm`
    (or to the requesting tool) to approve the operation.
    """

    def __init__(
        self,
        message: str,
        token: Optional[str] = None,
        decision: Optional[PermissionDecision] = None,
    ) -> None:
        super().__init__(message)
        self.token = token
        self.decision = decision

class PermissionManager:
    """Enforces the security policy for every subsystem operation."""

    def __init__(
        self,
        policy: SecurityPolicy,
        *,
        event_bus: Any = None,
        state_store: Any = None,
        memory: Any = None,
    ) -> None:
        self.policy = policy
        self._event_bus = event_bus
        self._state = state_store
        self._memory = memory
        self._pending: Dict[str, tuple] = {}  # token -> (decision, issued_at)
        self._audit: List[PermissionDecision] = []
        self._audit_cap = 500

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #
    def check(
        self,
        action: Any,
        *,
        source: Any = None,
        destination: Any = None,
        actor: str = "user",
        command: Optional[str] = None,
        cwd: Any = None,
        shell: bool = False,
        recursive: bool = False,
        workspace: Optional[str] = None,
        auto_confirm: Optional[bool] = None,
    ) -> PermissionDecision:
        """Evaluate one operation and return a :class:`PermissionDecision`."""
        name = action.value if isinstance(action, FileOperationKind) else str(action)
        if name == FileOperationKind.EXECUTE_COMMAND.value:
            return self._check_command(
                command=command,
                cwd=cwd,
                shell=shell,
                actor=actor,
                workspace=workspace,
                auto_confirm=auto_confirm,
            )

        source_path = self._resolve(source)
        dest_path = self._resolve(destination)
        resolved_workspace = workspace or self._workspace_name(source_path) or self._workspace_name(dest_path)

        # 1. System-critical paths are always denied ------------------------- #
        for candidate in (source_path, dest_path):
            if candidate is not None and self.policy.is_system_path(candidate):
                return self._deny(
                    name,
                    f"path is system-critical and denied by policy: {candidate}",
                    DangerLevel.CRITICAL,
                    actor=actor,
                    source=source_path,
                    destination=dest_path,
                    workspace=resolved_workspace,
                )

        # 2. Path containment ------------------------------------------------- #
        for candidate in (source_path, dest_path):
            if candidate is None:
                continue
            if not (self.policy.is_allowlisted(candidate) or self.policy.contains_workspace(candidate)):
                return self._deny(
                    name,
                    f"path is outside the approved workspace: {candidate}",
                    DangerLevel.HIGH,
                    actor=actor,
                    source=source_path,
                    destination=dest_path,
                    workspace=resolved_workspace,
                )

        # 3. Protected paths (destructive ops only) --------------------------- #
        danger = KIND_DANGER.get(action, DangerLevel.MEDIUM)
        if action in DESTRUCTIVE_KINDS:
            for candidate in (source_path, dest_path):
                if candidate is not None and self.policy.is_protected(candidate):
                    return self._deny(
                        name,
                        f"path is protected and cannot be modified: {candidate}",
                        DangerLevel.CRITICAL,
                        actor=actor,
                        source=source_path,
                        destination=dest_path,
                        workspace=resolved_workspace,
                    )

        # 4. Danger escalation ------------------------------------------------ #
        if name == FileOperationKind.DELETE_FOLDER.value and recursive:
            danger = DangerLevel.CRITICAL
        needs_confirmation = danger in (DangerLevel.HIGH, DangerLevel.CRITICAL)
        if actor == "agent" and danger.value in ("medium", "high", "critical"):
            needs_confirmation = True

        confirm_override = self.policy.auto_confirm if auto_confirm is None else auto_confirm
        if needs_confirmation and confirm_override and actor != "agent":
            decision = self._allow(
                name,
                f"auto-confirmed ({danger.value})",
                danger,
                actor=actor,
                source=source_path,
                destination=dest_path,
                workspace=resolved_workspace,
            )
            decision.confirmed = True
            self._record(decision)
            return decision

        if needs_confirmation:
            return self._issue_confirmation(
                name,
                f"operation requires explicit user confirmation ({danger.value})",
                danger,
                actor=actor,
                source=source_path,
                destination=dest_path,
                workspace=resolved_workspace,
            )

        decision = self._allow(
            name,
            f"operation is allowed ({danger.value})",
            danger,
            actor=actor,
            source=source_path,
            destination=dest_path,
            workspace=resolved_workspace,
        )
        self._record(decision)
        return decision


    # ----------------------------------------------------------------------- #
    # Command checks
    # ----------------------------------------------------------------------- #
    def _check_command(
        self,
        *,
        command: Optional[str],
        cwd: Any,
        shell: bool,
        actor: str,
        workspace: Optional[str],
        auto_confirm: Optional[bool],
    ) -> PermissionDecision:
        name = FileOperationKind.EXECUTE_COMMAND.value
        text = (command or "").strip()
        if not text:
            return self._deny(name, "empty command", DangerLevel.HIGH, actor=actor, workspace=workspace)

        review = self.policy.evaluate_command(text, shell=shell)
        cwd_path = self._resolve(cwd)

        # Command must be issued inside an approved workspace.
        if cwd_path is not None and not (
            self.policy.is_allowlisted(cwd_path) or self.policy.contains_workspace(cwd_path)
        ):
            return self._deny(
                name,
                f"command working directory is outside the approved workspace: {cwd_path}",
                DangerLevel.HIGH,
                actor=actor,
                command=text,
                source=str(cwd_path),
                workspace=workspace,
            )

        resolved_workspace = workspace or self._workspace_name(cwd_path)

        # Always-denied commands bypass confirmation entirely.
        if review.always_deny:
            return self._deny(
                name,
                review.reason,
                DangerLevel.CRITICAL,
                actor=actor,
                command=text,
                source=str(cwd_path) if cwd_path else None,
                workspace=resolved_workspace,
            )

        # Any command issued by an agent needs user confirmation.
        needs_confirmation = actor == "agent" or shell or review.danger_level in (
            DangerLevel.HIGH,
            DangerLevel.CRITICAL,
        )

        confirm_override = self.policy.auto_confirm if auto_confirm is None else auto_confirm
        if needs_confirmation and confirm_override and actor != "agent":
            decision = self._allow(
                name,
                f"auto-confirmed command ({review.reason})",
                review.danger_level,
                actor=actor,
                command=text,
                source=str(cwd_path) if cwd_path else None,
                workspace=resolved_workspace,
            )
            decision.confirmed = True
            self._record(decision)
            return decision

        if needs_confirmation:
            return self._issue_confirmation(
                name,
                review.reason,
                review.danger_level,
                actor=actor,
                command=text,
                source=str(cwd_path) if cwd_path else None,
                workspace=resolved_workspace,
            )

        decision = self._allow(
            name,
            review.reason,
            review.danger_level,
            actor=actor,
            command=text,
            source=str(cwd_path) if cwd_path else None,
            workspace=resolved_workspace,
        )
        self._record(decision)
        return decision


    # ----------------------------------------------------------------------- #
    # Decision helpers
    # ----------------------------------------------------------------------- #
    def _allow(
        self,
        action: str,
        reason: str,
        danger: DangerLevel,
        *,
        actor: str,
        source: Any = None,
        destination: Any = None,
        command: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> PermissionDecision:
        return PermissionDecision(
            action=action,
            actor=actor,
            allowed=True,
            requires_confirmation=False,
            reason=reason,
            danger_level=danger,
            source=str(source) if source is not None else None,
            destination=str(destination) if destination is not None else None,
            command=command,
            workspace=workspace,
        )

    def _deny(
        self,
        action: str,
        reason: str,
        danger: DangerLevel,
        *,
        actor: str,
        source: Any = None,
        destination: Any = None,
        command: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> PermissionDecision:
        decision = PermissionDecision(
            action=action,
            actor=actor,
            allowed=False,
            requires_confirmation=False,
            reason=reason,
            danger_level=danger,
            source=str(source) if source is not None else None,
            destination=str(destination) if destination is not None else None,
            command=command,
            workspace=workspace,
        )
        self._record(decision)
        return decision

    def _issue_confirmation(
        self,
        action: str,
        reason: str,
        danger: DangerLevel,
        *,
        actor: str,
        source: Any = None,
        destination: Any = None,
        command: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> PermissionDecision:
        token = secrets.token_urlsafe(24)
        expires_at = time.time() + self.policy.confirmation_ttl_seconds
        decision = PermissionDecision(
            action=action,
            actor=actor,
            allowed=False,
            requires_confirmation=True,
            reason=reason,
            danger_level=danger,
            source=str(source) if source is not None else None,
            destination=str(destination) if destination is not None else None,
            command=command,
            workspace=workspace,
            token=token,
            expires_at=expires_at,
        )
        self._pending[token] = (decision, time.time())
        self._record(decision)
        return decision

    def _record(self, decision: PermissionDecision) -> None:
        """Mirror a decision to the audit trail, event bus, state and memory."""
        self._audit.append(decision)
        if len(self._audit) > self._audit_cap:
            self._audit = self._audit[-self._audit_cap :]
        event = (
            EV_PERMISSION_CONFIRMED
            if decision.confirmed
            else EV_PERMISSION_DENIED if not decision.allowed and not decision.requires_confirmation
            else EV_PERMISSION_CHECKED
        )
        emit_automation_event(event, decision.as_dict(), bus=self._event_bus)
        if self._state is not None:
            try:
                self._state.update("automation.last_permission", decision.as_dict())
            except Exception:  # noqa: BLE001
                pass
        if self._memory is not None:
            try:
                self._memory.store(
                    self._memory_context(decision.workspace or "default"),
                    f"permission:{time.time_ns():x}",
                    decision.as_dict(),
                    tags=["automation", "permissions"],
                )
            except Exception:  # noqa: BLE001
                pass


    # ----------------------------------------------------------------------- #
    # Confirmation flow
    # ----------------------------------------------------------------------- #
    def confirm(self, token: Optional[str], actor: str = "user") -> bool:
        """Approve a previously issued confirmation token.

        Returns ``True`` when the token is valid, not expired and approved.
        """
        if not token:
            return False
        entry = self._pending.pop(token, None)
        if entry is None:
            return False
        decision, issued_at = entry
        if time.time() > issued_at + self.policy.confirmation_ttl_seconds:
            return False  # expired
        decision.allowed = True
        decision.requires_confirmation = False
        decision.confirmed = True
        decision.confirmed_by = actor
        self._record(decision)
        return True

    def revoke(self, token: Optional[str]) -> bool:
        """Invalidate a pending confirmation token."""
        return self._pending.pop(token, None) is not None

    def pending(self) -> List[Dict[str, Any]]:
        """List all un-expired pending confirmations (for the approval UI)."""
        now = time.time()
        result: List[Dict[str, Any]] = []
        for token, (decision, issued_at) in list(self._pending.items()):
            if now > issued_at + self.policy.confirmation_ttl_seconds:
                self._pending.pop(token, None)
                continue
            data = decision.as_dict()
            data["token"] = token
            result.append(data)
        return result

    def audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent permission decisions (newest first)."""
        return [d.as_dict() for d in self._audit[-limit:]][::-1]

    # ----------------------------------------------------------------------- #
    # Workspace management
    # ----------------------------------------------------------------------- #
    def register_workspace(self, root: Any, *, name: Optional[str] = None, allowed: bool = True) -> WorkspaceProfile:
        """Register an additional approved workspace at runtime."""
        resolved = Path(root).expanduser().resolve()
        profile = WorkspaceProfile(name=name or resolved.name, root=resolved, allowed=allowed)
        self.policy._profiles.append(profile)
        if resolved not in self.policy.workspace_roots:
            self.policy.workspace_roots.append(resolved)
        logger.info(f"Registered workspace: {profile.as_dict()}")
        return profile

    def allow_path(self, path: Any) -> Path:
        """Explicitly allow a path that lives outside the workspace roots."""
        return self.policy.allow_path(path)

    # ----------------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------------- #
    @staticmethod
    def _resolve(path: Any) -> Optional[Path]:
        if path is None:
            return None
        try:
            return Path(path).expanduser().resolve()
        except (TypeError, ValueError):
            return None

    def _workspace_name(self, path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        profile = self.policy.workspace_for(path)
        return profile.name if profile else None

    def _memory_context(self, workspace: str):
        try:
            from memory import MemoryContext, MemoryScope

            return MemoryContext(scope=MemoryScope.WORKSPACE, scope_id=workspace)
        except Exception:  # noqa: BLE001
            return None

