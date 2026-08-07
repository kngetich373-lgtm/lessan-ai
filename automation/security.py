"""Security policy for the File & Command Control System.

The :class:`SecurityPolicy` is the single source of truth for what the
subsystem may touch:

* **workspace roots** — the only directories where file operations and
  command execution may occur (path containment);
* **system-critical roots** — always denied (``/etc``, ``/usr``, ...);
* **protected paths** — files/folders that must not be deleted, moved or
  overwritten accidentally (the Lessan AI source tree, config, keys);
* **command signatures** — always-denied commands (``rm -rf /``) and
  confirmation-required patterns (``curl | sh``, ``sudo``, ``mkfs``).

The policy is derived from the ``automation`` section of the Lessan
configuration with safe defaults, and can be extended at runtime through
:meth:`SecurityPolicy.allow_path` and :class:`WorkspaceProfile`.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger

from automation.models import (
    CommandReview,
    DangerLevel,
    WorkspaceProfile,
)

logger = get_logger("automation.security")


def _expand(value: str) -> Path:
    """Expand ``~`` and env vars and resolve a path."""
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


# --------------------------------------------------------------------------- #
# Default policy data
# --------------------------------------------------------------------------- #

#: Default approved workspace roots (``~`` is expanded at construction time).
DEFAULT_WORKSPACE_ROOTS = (
    "~/Desktop",
    "~/Documents",
    "~/Downloads",
    "~/Lessan",
)

#: System-critical roots that are always denied, whatever the actor.
DEFAULT_SYSTEM_DENY_ROOTS = (
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys",
    "/dev", "/var", "/root", "/lib", "/lib64", "/opt", "/snap",
    "~/.ssh", "~/.gnupg", "~/.config", "~/.aws", "~/.cache", "~/.local",
)

#: Path fragments that must never be deleted/moved/overwritten.
DEFAULT_PROTECTED_PATHS = (
    ".git", ".env", ".venv", "node_modules", "__pycache__",
    "main.py", "lessan_ui.py", "requirements.txt", "setup.py", "pyproject.toml",
    "config", "core", "memory", "documents", "automation", "agents",
    "packaging", "workspaces", "plugins", "scripts",
)

#: Command fragments that can never be executed, no matter the confirmation.
ALWAYS_DENY_COMMAND_PATTERNS = (
    re.compile(r"(^|[;&|]\s*)rm\s+-[a-z]*r[a-z]*f[a-z]*\s+(/|~|--no-preserve-root|\$HOME|\$/)"),
    re.compile(r"(^|[;&|]\s*)rm\s+-[a-z]*f[a-z]*r[a-z]*\s+(/|~|--no-preserve-root|\$HOME|\$/)"),
    re.compile(r"(^|[;&|]\s*)rm\s+-[a-z]*rf[a-z]*\s+(\$HOME|\$|\/)\s*$"),
    re.compile(r"(^|[;&|]\s*)mkfs(\.\w+)?\s+"),
    re.compile(r"(^|[;&|]\s*)(fdisk|gdisk|cfdisk|parted)\s+"),
    re.compile(r"(^|[;&|]\s*)dd\s+.*of=/dev/(sd|hd|nvme)"),
    re.compile(r"(^|[;&|]\s*)(shutdown|reboot|halt|poweroff)\s+"),
    re.compile(r"(^|[;&|]\s*)init\s+[06]\s*"),
    re.compile(r":\(\)\s*\{"),
    re.compile(r"(curl|wget)\s+[^;&|]*\|\s*(ba)?sh\s*$"),
)

#: Fragments that force explicit user confirmation (destructive or affecting
#: the system beyond the workspace).
DANGEROUS_COMMAND_PATTERNS = (
    re.compile(r"(^|[;&|]\s*)(sudo|su\s+-)\s+"),
    re.compile(r"(^|[;&|]\s*)chmod\s+[0-7]{4}\s"),
    re.compile(r"(^|[;&|]\s*)chown\s+"),
    re.compile(r"(^|[;&|]\s*)rm\s+-[a-z]*[rf][a-z]*"),
    re.compile(r"(^|[;&|]\s*)(apt|apt-get|dnf|yum|pacman|brew|port)\s+"),
    re.compile(r"(^|[;&|]\s*)git\s+(reset|clean)"),
    re.compile(r"(^|[;&|]\s*)git\s+push\s+[^;|&]*(--force|-f)"),
    re.compile(r"(^|[;&|]\s*)docker\s+"),
    re.compile(r"(^|[;&|]\s*)mkfs"),
)

#: Danger level of each known command binary. Unknown binaries always
#: require explicit user confirmation.
DEFAULT_COMMAND_LEVELS: Dict[str, DangerLevel] = {
    "python": DangerLevel.LOW, "python3": DangerLevel.LOW,
    "pip": DangerLevel.LOW, "pip3": DangerLevel.LOW,
    "npm": DangerLevel.LOW, "npx": DangerLevel.LOW, "node": DangerLevel.LOW,
    "yarn": DangerLevel.LOW, "pnpm": DangerLevel.LOW,
    "git": DangerLevel.LOW, "pytest": DangerLevel.LOW, "pandoc": DangerLevel.LOW,
    "ls": DangerLevel.LOW, "cat": DangerLevel.LOW, "echo": DangerLevel.LOW,
    "mkdir": DangerLevel.LOW, "touch": DangerLevel.LOW, "cp": DangerLevel.LOW,
    "head": DangerLevel.LOW, "tail": DangerLevel.LOW, "grep": DangerLevel.LOW,
    "rg": DangerLevel.LOW, "find": DangerLevel.LOW, "sed": DangerLevel.LOW,
    "awk": DangerLevel.LOW, "wc": DangerLevel.LOW, "sort": DangerLevel.LOW,
    "uniq": DangerLevel.LOW, "date": DangerLevel.LOW, "pwd": DangerLevel.LOW,
    "du": DangerLevel.LOW, "df": DangerLevel.LOW, "uname": DangerLevel.LOW,
    "hostname": DangerLevel.LOW, "curl": DangerLevel.LOW, "wget": DangerLevel.LOW,
    "zip": DangerLevel.LOW, "unzip": DangerLevel.LOW,
    "mv": DangerLevel.MEDIUM, "rename": DangerLevel.MEDIUM,
    "make": DangerLevel.MEDIUM, "tar": DangerLevel.MEDIUM, "rmdir": DangerLevel.MEDIUM,
    "trash": DangerLevel.MEDIUM,
    "rm": DangerLevel.HIGH, "docker": DangerLevel.HIGH,
    "bash": DangerLevel.HIGH, "sh": DangerLevel.HIGH,
    "zsh": DangerLevel.HIGH, "fish": DangerLevel.HIGH,
}

COMMAND_DESCRIPTIONS: Dict[str, str] = {
    "python": "Run a Python script or snippet",
    "python3": "Run a Python 3 script or snippet",
    "pip": "Install or manage Python packages",
    "pip3": "Install or manage Python 3 packages",
    "npm": "Install or manage Node packages",
    "npx": "Run a Node package binary",
    "node": "Run a Node.js script",
    "git": "Version control operations",
    "pytest": "Run the test suite",
    "make": "Run a build via Makefile",
    "docker": "Run Docker containers (requires confirmation)",
    "pandoc": "Convert documents",
    "rm": "Remove files (requires confirmation)",
    "mv": "Move files",
    "cp": "Copy files",
    "ls": "List directory contents",
    "cat": "Print file contents",
    "echo": "Print text",
    "bash": "Run a bash snippet (requires confirmation)",
    "sh": "Run a shell snippet (requires confirmation)",
    "curl": "Transfer data from a URL",
    "wget": "Download from a URL",
}


def _config_value(config: Any, key: str, default: Any) -> Any:
    """Read ``automation.<key>`` from a ConfigManager or a plain dict."""
    if config is None:
        return default
    if isinstance(config, dict):
        section = config.get("automation") or {}
        return section.get(key, default)
    getter = getattr(config, "get", None)
    if getter is None:
        return default
    try:
        value = getter(f"automation.{key}", None)
    except Exception:  # noqa: BLE001 - config read must never crash policy
        return default
    return default if value is None else value


class SecurityPolicy:
    """Single source of truth for what the subsystem is allowed to touch.

    Safe defaults are applied for every dimension, so a policy can be
    constructed with no arguments; explicit values always win over config
    values, which win over built-in defaults.
    """

    def __init__(
        self,
        *,
        config: Any = None,
        workspace_roots: Optional[List[str]] = None,
        app_root: Optional[str] = None,
        protected_paths: Optional[List[str]] = None,
        system_deny_roots: Optional[List[str]] = None,
        confirmation_ttl_seconds: Optional[float] = None,
        auto_confirm: Optional[bool] = None,
    ) -> None:
        from core.configuration.config import BASE_DIR

        self._config = config

        # Workspace roots ---------------------------------------------------- #
        roots = list(workspace_roots) if workspace_roots else list(
            _config_value(config, "workspace_roots", None) or DEFAULT_WORKSPACE_ROOTS
        )
        app_root_value = app_root or _config_value(config, "app_root", None)
        self._app_root = _expand(app_root_value) if app_root_value else Path(BASE_DIR).resolve()
        if str(self._app_root) not in {str(_expand(r)) for r in roots}:
            roots.insert(0, str(self._app_root))
        self.workspace_roots: List[Path] = []
        seen: set = set()
        self._profiles: List[WorkspaceProfile] = []
        for index, raw in enumerate(roots):
            root = _expand(raw)
            if str(root) in seen:
                continue
            seen.add(str(root))
            self.workspace_roots.append(root)
            self._profiles.append(WorkspaceProfile(name=f"workspace_{index}", root=root))
        self._profiles.insert(0, WorkspaceProfile(name="app", root=self._app_root))

        # System-critical roots ----------------------------------------------- #
        deny = list(system_deny_roots) if system_deny_roots else list(
            _config_value(config, "system_deny_roots", None) or DEFAULT_SYSTEM_DENY_ROOTS
        )
        self._system_deny_roots = [_expand(p) for p in deny]
        self._deny_set = set(self._system_deny_roots)

        # Protected paths ----------------------------------------------------- #
        protected = list(protected_paths) if protected_paths else list(
            _config_value(config, "protected_paths", None) or DEFAULT_PROTECTED_PATHS
        )
        self._protected_patterns = tuple(protected)

        # Confirmation / auto-approval ---------------------------------------- #
        ttl = confirmation_ttl_seconds
        if ttl is None:
            ttl = _config_value(config, "confirmation_ttl_seconds", 120.0)
        self.confirmation_ttl_seconds = float(ttl)
        self.auto_confirm = bool(
            auto_confirm if auto_confirm is not None
            else _config_value(config, "auto_confirm", False)
        )

        # Allowlist and registered command levels ------------------------------ #
        self._allowlist: set = set()
        self._command_registry: Any = None
        self._extra_command_levels: Dict[str, DangerLevel] = {}
        logger.info(
            f"SecurityPolicy ready: {len(self.workspace_roots)} workspace(s), "
            f"{len(self._system_deny_roots)} deny root(s), auto_confirm={self.auto_confirm}"
        )


    # ----------------------------------------------------------------------- #
    # Properties
    # ----------------------------------------------------------------------- #
    @property
    def app_root(self) -> Path:
        """The Lessan AI application root (always a workspace)."""
        return self._app_root

    @property
    def profiles(self) -> List[WorkspaceProfile]:
        return list(self._profiles)

    @property
    def command_registry(self) -> Any:
        return self._command_registry

    @command_registry.setter
    def command_registry(self, registry: Any) -> None:
        self._command_registry = registry

    @property
    def auto_confirm_enabled(self) -> bool:
        return bool(self.auto_confirm)

    # ----------------------------------------------------------------------- #
    # Workspace containment
    # ----------------------------------------------------------------------- #
    def workspace_for(self, path: Any) -> Optional[WorkspaceProfile]:
        """Return the profile whose root contains ``path`` (or ``None``)."""
        resolved = Path(path).resolve()
        for profile in self._profiles:
            if profile.contains(resolved):
                return profile
        return None

    def contains_workspace(self, path: Any) -> bool:
        return self.workspace_for(path) is not None

    def is_allowlisted(self, path: Any) -> bool:
        return Path(path).resolve() in self._allowlist

    def allow_path(self, path: Any) -> Path:
        """Add an explicit allowlist entry (outside the workspace roots)."""
        resolved = Path(path).resolve()
        self._allowlist.add(resolved)
        logger.info(f"Allowlisted path: {resolved}")
        return resolved

    def is_system_path(self, path: Any) -> bool:
        """True when ``path`` sits inside a system-critical root."""
        resolved = Path(path).resolve()
        for root in self._deny_set:
            if resolved == root or root in resolved.parents:
                return True
        return False

    def is_protected(self, path: Any) -> bool:
        """True when a path must never be deleted/moved/overwritten.

        A path is protected when it is allowlisted (explicit exception) or
        when any of its parts matches a protected pattern (``.git``,
        ``config``, ``core``, ``main.py``, ``node_modules``, ...).
        """
        if self.is_allowlisted(path):
            return False
        resolved = Path(path).resolve()
        for root in self.workspace_roots:
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            for part in relative.parts:
                if part in self._protected_patterns:
                    return True
                for pattern in self._protected_patterns:
                    if pattern.startswith(".") and fnmatch.fnmatch(part, pattern):
                        return True
            return False
        return False


    # ----------------------------------------------------------------------- #
    # Command review
    # ----------------------------------------------------------------------- #
    def register_command_level(self, name: str, danger_level: DangerLevel) -> None:
        """Register an additional known command binary and its danger level."""
        self._extra_command_levels[name] = danger_level

    def _command_level(self, name: str) -> Optional[DangerLevel]:
        if self._command_registry is not None:
            spec = self._command_registry.lookup(name)
            if spec is not None:
                return spec.danger_level
        if name in self._extra_command_levels:
            return self._extra_command_levels[name]
        return DEFAULT_COMMAND_LEVELS.get(name)

    def evaluate_command(self, command: str, shell: bool = False) -> CommandReview:
        """Assess a command string and return a :class:`CommandReview`."""
        text = (command or "").strip()
        if not text:
            return CommandReview(DangerLevel.SAFE, "empty command")
        for pattern in ALWAYS_DENY_COMMAND_PATTERNS:
            if pattern.search(text):
                return CommandReview(
                    DangerLevel.CRITICAL,
                    "command is always denied by policy",
                    always_deny=True,
                )
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if pattern.search(text):
                return CommandReview(
                    DangerLevel.HIGH,
                    "command matches a dangerous signature",
                )
        if shell:
            return CommandReview(
                DangerLevel.HIGH,
                "shell-mode commands require confirmation",
            )
        try:
            argv = shlex.split(text)
        except ValueError:
            return CommandReview(
                DangerLevel.HIGH,
                "command could not be parsed safely",
            )
        if not argv:
            return CommandReview(DangerLevel.SAFE, "empty command")
        name = argv[0]
        level = self._command_level(name)
        if level is None:
            return CommandReview(
                DangerLevel.HIGH,
                f"unknown command '{name}' requires confirmation",
            )
        return CommandReview(level, f"known command '{name}'")

    def as_dict(self) -> Dict[str, Any]:
        """Serialise the policy for tooling and the state store."""
        return {
            "app_root": str(self._app_root),
            "workspace_roots": [str(r) for r in self.workspace_roots],
            "profiles": [p.as_dict() for p in self._profiles],
            "system_deny_roots": [str(r) for r in self._system_deny_roots],
            "protected_patterns": list(self._protected_patterns),
            "confirmation_ttl_seconds": self.confirmation_ttl_seconds,
            "auto_confirm": self.auto_confirm,
            "allowlisted": [str(p) for p in sorted(self._allowlist)],
        }

