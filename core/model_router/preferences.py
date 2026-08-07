"""Provider Preference Manager — user overrides for provider selection."""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.logging import get_logger

logger = get_logger("PreferenceManager")

DEFAULT_PREFS_FILE = Path.home() / ".local" / "share" / "lessan" / "provider_preferences.json"


@dataclass
class ProviderPreferences:
    """User preferences for provider selection."""
    
    disabled_providers: Set[str] = field(default_factory=set)
    priority_overrides: Dict[str, int] = field(default_factory=dict)
    forced_provider: Optional[str] = None
    local_only: bool = False
    cloud_only: bool = False
    
    def as_dict(self) -> Dict:
        return {
            "disabled_providers": list(self.disabled_providers),
            "priority_overrides": self.priority_overrides,
            "forced_provider": self.forced_provider,
            "local_only": self.local_only,
            "cloud_only": self.cloud_only,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ProviderPreferences":
        return cls(
            disabled_providers=set(data.get("disabled_providers", [])),
            priority_overrides=data.get("priority_overrides", {}),
            forced_provider=data.get("forced_provider"),
            local_only=data.get("local_only", False),
            cloud_only=data.get("cloud_only", False),
        )


class ProviderPreferenceManager:
    """Manages user preferences for provider selection."""
    
    def __init__(self, storage_path: Optional[Path] = None) -> None:
        # Accept either Path or str for convenience.
        if isinstance(storage_path, str):
            storage_path = Path(storage_path)
        self._storage_path = storage_path or DEFAULT_PREFS_FILE
        self._prefs = ProviderPreferences()
        self._lock = threading.RLock()
        self._load()
    
    def disable_provider(self, name: str) -> None:
        """Disable a provider."""
        with self._lock:
            self._prefs.disabled_providers.add(name)
            self._save()
    
    def enable_provider(self, name: str) -> None:
        """Enable a previously disabled provider."""
        with self._lock:
            self._prefs.disabled_providers.discard(name)
            self._save()
    
    def set_priority_override(self, name: str, priority: int) -> None:
        """Override provider priority."""
        with self._lock:
            self._prefs.priority_overrides[name] = priority
            self._save()
    
    def clear_priority_override(self, name: str) -> None:
        """Remove priority override."""
        with self._lock:
            self._prefs.priority_overrides.pop(name, None)
            self._save()
    
    def set_forced_provider(self, name: Optional[str]) -> None:
        """Force a specific provider (None to clear)."""
        with self._lock:
            self._prefs.forced_provider = name
            self._save()
    
    def set_local_only(self, enabled: bool) -> None:
        """Enable/disable local-only mode."""
        with self._lock:
            self._prefs.local_only = enabled
            if enabled:
                self._prefs.cloud_only = False
            self._save()
    
    def set_cloud_only(self, enabled: bool) -> None:
        """Enable/disable cloud-only mode."""
        with self._lock:
            self._prefs.cloud_only = enabled
            if enabled:
                self._prefs.local_only = False
            self._save()
    
    def is_provider_enabled(self, name: str) -> bool:
        """Check if a provider is enabled."""
        with self._lock:
            return name not in self._prefs.disabled_providers
    
    def get_priority_override(self, name: str) -> Optional[int]:
        """Get priority override for a provider."""
        with self._lock:
            return self._prefs.priority_overrides.get(name)
    
    def get_forced_provider(self) -> Optional[str]:
        """Get forced provider name."""
        with self._lock:
            return self._prefs.forced_provider
    
    def is_local_only(self) -> bool:
        with self._lock:
            return self._prefs.local_only
    
    def is_cloud_only(self) -> bool:
        with self._lock:
            return self._prefs.cloud_only
    
    def get_disabled_providers(self) -> List[str]:
        with self._lock:
            return list(self._prefs.disabled_providers)
    
    def reset(self) -> None:
        """Reset all preferences to defaults."""
        with self._lock:
            self._prefs = ProviderPreferences()
            self._save()
    
    def _load(self) -> None:
        if not self._storage_path.exists():
            logger.info("No preferences file found, using defaults")
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._prefs = ProviderPreferences.from_dict(data)
            logger.info("Loaded provider preferences")
        except Exception as exc:
            logger.warning(f"Failed to load preferences: {exc}")
    
    def _save(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._prefs.as_dict(), f, indent=2)
            logger.debug("Saved provider preferences")
        except Exception as exc:
            logger.error(f"Failed to save preferences: {exc}")
