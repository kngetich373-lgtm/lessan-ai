"""Centralized configuration management for Lessan AI."""

import json
import os
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
DEFAULT_CONFIG_FILE = CONFIG_DIR / "lessan_config.json"
API_KEYS_FILE = CONFIG_DIR / "api_keys.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "Lessan AI",
        "version": "1.0.0",
        "verbose": False,
    },
    "ui": {
        "theme": "Galaxy Diamond Nebula",
        "min_width": 1200,
        "min_height": 800,
    },
    "models": {
        "default_provider": "gemini",
        "fallback_providers": ["openrouter", "omniroute", "ollama"],
        "live_model": "models/gemini-2.5-flash-native-audio-preview-12-2025",
        "temperature": 0.4,
        "max_tokens": 4096,
    },
    # Model Router configuration. Provider adapters register themselves
    # through the DI container; these values tune the router behaviour only.
    "model_router": {
        "max_fallbacks": 3,
        "health": {
            "check_interval": 60.0,
            "timeout": 5.0,
        },
        "weights": {
            "priority": 0.25,
            "health": 0.25,
            "cost": 0.20,
            "latency": 0.15,
            "context": 0.10,
            "capability": 0.05,
        },
    },
    "voice": {
        "enabled": True,
        "voice_name": "Charon",
        "channels": 1,
        "send_sample_rate": 16000,
        "receive_sample_rate": 24000,
        "chunk_size": 1024,
        "wake_word": "Lessan",
    },
    "vision": {
        "enabled": True,
        "ocr_language": "eng",
        "save_screenshots": False,
        "screenshot_dir": "reports/screenshots",
    },
    "memory": {
        "enabled": True,
        "max_chars": 2200,
        "auto_extract": True,
        "conversation_history_days": 7,
    },
    "scheduler": {
        "enabled": True,
        "tick_seconds": 1.0,
    },
    "plugins": {
        "directory": "plugins",
        "auto_discover": True,
    },
    "security": {
        "sandbox_enabled": True,
        "audit_log_enabled": True,
    },
    # File & Command Control System (automation/).
    # The subsystem reads these through SecurityPolicy / automation.di with
    # safe defaults, so the section is entirely optional.
    "automation": {
        # Directories where file operations and command execution may occur.
        "workspace_roots": [
            "~/Desktop",
            "~/Documents",
            "~/Downloads",
            "~/Lessan",
        ],
        # Application root for the subsystem; None resolves to BASE_DIR.
        "app_root": None,
        # System-critical roots that are always denied (expanded at runtime).
        "system_deny_roots": [
            "/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys",
            "/dev", "/var", "/root", "/lib", "/lib64", "/opt", "/snap",
            "~/.ssh", "~/.gnupg", "~/.config", "~/.aws", "~/.cache",
            "~/.local",
        ],
        # Path fragments that must never be deleted/moved/overwritten.
        "protected_paths": [
            ".git", ".env", ".venv", "node_modules", "__pycache__",
            "main.py", "lessan_ui.py", "requirements.txt", "setup.py",
            "pyproject.toml", "config", "core", "memory", "documents",
            "automation", "agents", "packaging", "workspaces", "plugins",
            "scripts",
        ],
        # How long an issued confirmation token stays valid (seconds).
        "confirmation_ttl_seconds": 120.0,
        # Auto-approve high/critical operations without a user token.
        "auto_confirm": False,
        # Soft-delete files to workspace/.trash instead of permanent removal.
        "trash_enabled": True,
        # Caps for read_file / search snippets and command output.
        "max_file_read_chars": 100000,
        "max_output_chars": 100000,
        # Default command timeout and recent-command history size.
        "command_timeout_seconds": 60.0,
        "max_history": 200,
        # Background FileWatcher polling (opt-in; see automation/watcher.py).
        "watch_enabled": False,
        "watch_interval_seconds": 2.0,
    },
    "paths": {
        "reports": "reports",
        "downloads": "downloads",
    },
}


class ConfigManager:
    """Thread-safe JSON-backed configuration manager.

    Provides dot-notation access (``config.get("models.temperature")``),
    environment variable overrides (``LESSAN__SECTION__KEY``), persistence
    to ``config/lessan_config.json``, and backward-compatible access to the
    legacy ``config/api_keys.json``.
    """

    def __init__(self, config_file: Path = DEFAULT_CONFIG_FILE) -> None:
        self._file = config_file
        self._data: Dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        self._lock = threading.RLock()
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Loading / saving
    # ------------------------------------------------------------------ #
    def load(self) -> "ConfigManager":
        """Load configuration from disk and apply env overrides."""
        with self._lock:
            self._load_file()
            self._apply_env_overrides()
            self._loaded = True
        return self

    def save(self) -> None:
        """Persist the current configuration to disk."""
        with self._lock:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def reset(self) -> None:
        """Reset all values to the defaults."""
        with self._lock:
            self._data = deepcopy(DEFAULT_CONFIG)
        self.save()

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by dot notation (e.g. ``models.temperature``)."""
        with self._lock:
            node: Any = self._data
            for part in key.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return default
            return deepcopy(node)

    def set(self, key: str, value: Any) -> "ConfigManager":
        """Set a value by dot notation and persist."""
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts[:-1]:
                if part not in node or not isinstance(node[part], dict):
                    node[part] = {}
                node = node[part]
            node[parts[-1]] = deepcopy(value)
        self.save()
        return self

    def section(self, name: str) -> Dict[str, Any]:
        """Return a copy of a top-level section."""
        with self._lock:
            return deepcopy(self._data.get(name, {}))

    def all(self) -> Dict[str, Any]:
        """Return a deep copy of the entire configuration."""
        with self._lock:
            return deepcopy(self._data)

    def update_section(self, name: str, values: Dict[str, Any]) -> "ConfigManager":
        """Merge values into a top-level section and persist."""
        with self._lock:
            if name not in self._data or not isinstance(self._data[name], dict):
                self._data[name] = {}
            self._data[name].update(deepcopy(values))
        self.save()
        return self

    # ------------------------------------------------------------------ #
    # API key compatibility helpers
    # ------------------------------------------------------------------ #
    def get_api_key(self, provider: str = "gemini") -> Optional[str]:
        """Read an API key from the legacy api_keys.json (compat layer)."""
        if not API_KEYS_FILE.exists():
            return None
        try:
            data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
            env_key = f"{provider}_api_key"
            # gemini → gemini_api_key; openai → openai_api_key; etc.
            if provider == "gemini":
                return data.get("gemini_api_key") or None
            return data.get(env_key) or data.get(provider) or None
        except Exception:
            return None

    def set_api_key(self, provider: str, api_key: str) -> None:
        """Write an API key to the legacy api_keys.json (compat layer)."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if API_KEYS_FILE.exists():
            try:
                data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if provider == "gemini":
            data["gemini_api_key"] = api_key.strip()
        else:
            data[f"{provider}_api_key"] = api_key.strip()
        API_KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_api_keys(self) -> Dict[str, str]:
        """Return all provider API keys without exposing secrets in logs."""
        if not API_KEYS_FILE.exists():
            return {}
        try:
            data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
            return {
                k: v
                for k, v in data.items()
                if isinstance(v, str) and len(v) > 0 and "key" in k.lower()
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------ #
    # Environment override support
    # ------------------------------------------------------------------ #
    def _apply_env_overrides(self) -> None:
        """Apply ``LESSAN__<SECTION>__<KEY>`` environment overrides."""
        for env_key, env_val in os.environ.items():
            if not env_key.startswith("LESSAN__"):
                continue
            parts = env_key.split("__")
            if len(parts) < 3:
                continue
            section = parts[1].lower()
            key = parts[2].lower()
            node = self._data.get(section)
            if not isinstance(node, dict):
                continue

            # Coerce common types
            try:
                if env_val in ("true", "True"):
                    node[key] = True
                elif env_val in ("false", "False"):
                    node[key] = False
                else:
                    node[key] = int(env_val)
            except ValueError:
                node[key] = env_val

    def _load_file(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._data = self._merge_deep(self._data, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[Config] ⚠️ Failed to load {self._file.name}: {exc}")

    @staticmethod
    def _merge_deep(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        result = deepcopy(base)
        for key, value in overrides.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._merge_deep(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result


# Global configuration instance
config = ConfigManager().load()