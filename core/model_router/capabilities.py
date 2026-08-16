"""Capability definitions and the central model capability registry.

Capability names are provider-neutral. Provider adapters publish normalized
model metadata here and routing consumes this registry as the authoritative
source for model-level capability metadata.
"""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Set, Tuple, Optional

from core.model_router.models import ModelCapabilities, ModelInfo

CAPABILITY_GENERAL_CHAT = "general_chat"
CAPABILITY_REASONING = "reasoning"
CAPABILITY_LONG_CONTEXT = "long_context"

CAPABILITY_PYTHON = "python"
CAPABILITY_JAVASCRIPT = "javascript"
CAPABILITY_TYPESCRIPT = "typescript"
CAPABILITY_JAVA = "java"
CAPABILITY_CPP = "cpp"
CAPABILITY_CSHARP = "csharp"
CAPABILITY_GO = "go"
CAPABILITY_RUST = "rust"
CAPABILITY_PHP = "php"
CAPABILITY_RUBY = "ruby"

CAPABILITY_FRONTEND_DEV = "frontend_development"
CAPABILITY_BACKEND_DEV = "backend_development"
CAPABILITY_FULLSTACK_DEV = "fullstack_development"
CAPABILITY_MOBILE_DEV = "mobile_development"
CAPABILITY_DEVOPS = "devops"
CAPABILITY_DATABASE = "database"

CAPABILITY_REACT = "react"
CAPABILITY_VUE = "vue"
CAPABILITY_ANGULAR = "angular"
CAPABILITY_FLUTTER = "flutter"
CAPABILITY_REACT_NATIVE = "react_native"
CAPABILITY_DJANGO = "django"
CAPABILITY_FLASK = "flask"
CAPABILITY_NODEJS = "nodejs"
CAPABILITY_SPRING = "spring"

CAPABILITY_SECURITY = "security"
CAPABILITY_DOCUMENTATION = "documentation"
CAPABILITY_DATA_ANALYSIS = "data_analysis"
CAPABILITY_MACHINE_LEARNING = "machine_learning"
CAPABILITY_WEB_SCRAPING = "web_scraping"
CAPABILITY_TESTING = "testing"
CAPABILITY_DEBUGGING = "debugging"
CAPABILITY_CODE_REVIEW = "code_review"
CAPABILITY_ARCHITECTURE = "architecture"
CAPABILITY_PERFORMANCE = "performance_optimization"

ALL_CAPABILITIES: Set[str] = {
    "text", "streaming", "vision", "tool_calling", "embeddings",
    "audio", "image_generation", "multilingual",
    CAPABILITY_GENERAL_CHAT, CAPABILITY_REASONING, CAPABILITY_LONG_CONTEXT,
    CAPABILITY_PYTHON, CAPABILITY_JAVASCRIPT, CAPABILITY_TYPESCRIPT,
    CAPABILITY_JAVA, CAPABILITY_CPP, CAPABILITY_CSHARP, CAPABILITY_GO,
    CAPABILITY_RUST, CAPABILITY_PHP, CAPABILITY_RUBY,
    CAPABILITY_FRONTEND_DEV, CAPABILITY_BACKEND_DEV, CAPABILITY_FULLSTACK_DEV,
    CAPABILITY_MOBILE_DEV, CAPABILITY_DEVOPS, CAPABILITY_DATABASE,
    CAPABILITY_REACT, CAPABILITY_VUE, CAPABILITY_ANGULAR,
    CAPABILITY_FLUTTER, CAPABILITY_REACT_NATIVE,
    CAPABILITY_DJANGO, CAPABILITY_FLASK, CAPABILITY_NODEJS, CAPABILITY_SPRING,
    CAPABILITY_SECURITY, CAPABILITY_DOCUMENTATION, CAPABILITY_DATA_ANALYSIS,
    CAPABILITY_MACHINE_LEARNING, CAPABILITY_WEB_SCRAPING,
    CAPABILITY_TESTING, CAPABILITY_DEBUGGING, CAPABILITY_CODE_REVIEW,
    CAPABILITY_ARCHITECTURE, CAPABILITY_PERFORMANCE,
}

CAPABILITY_GROUPS: Dict[str, List[str]] = {
    "web_frontend": [CAPABILITY_FRONTEND_DEV, CAPABILITY_JAVASCRIPT, CAPABILITY_TYPESCRIPT, CAPABILITY_REACT, CAPABILITY_VUE, CAPABILITY_ANGULAR],
    "web_backend": [CAPABILITY_BACKEND_DEV, CAPABILITY_PYTHON, CAPABILITY_NODEJS, CAPABILITY_JAVA, CAPABILITY_DATABASE, CAPABILITY_DJANGO, CAPABILITY_FLASK, CAPABILITY_SPRING],
    "mobile": [CAPABILITY_MOBILE_DEV, CAPABILITY_FLUTTER, CAPABILITY_REACT_NATIVE],
    "systems_programming": [CAPABILITY_CPP, CAPABILITY_RUST, CAPABILITY_GO, CAPABILITY_PERFORMANCE],
    "data_science": [CAPABILITY_PYTHON, CAPABILITY_DATA_ANALYSIS, CAPABILITY_MACHINE_LEARNING],
    "security": [CAPABILITY_SECURITY, CAPABILITY_CODE_REVIEW, CAPABILITY_DEBUGGING],
}


def expand_capability_groups(capabilities: List[str]) -> Set[str]:
    expanded: Set[str] = set()
    for cap in capabilities:
        expanded.update(CAPABILITY_GROUPS.get(cap, [cap]))
    return expanded


def validate_capabilities(capabilities: List[str]) -> List[str]:
    valid = []
    for cap in expand_capability_groups(capabilities):
        normalized = cap.lower().strip().replace("-", "_")
        if normalized in ALL_CAPABILITIES:
            valid.append(normalized)
    return sorted(valid)


class ModelCapabilityRegistry:
    """Thread-safe authoritative model-level capability registry."""

    def __init__(self) -> None:
        self._models: Dict[Tuple[str, str], ModelInfo] = {}
        self._lock = threading.RLock()

    def register_provider(self, provider: str, models: Iterable[ModelInfo]) -> None:
        """Replace all discovered model metadata for a provider."""
        provider = provider.strip()
        if not provider:
            return
        with self._lock:
            for key in [key for key in self._models if key[0] == provider]:
                del self._models[key]
            for model in models:
                if model.id:
                    self._models[(provider, model.id)] = model

    def register_model(self, provider: str, model: ModelInfo) -> None:
        if provider and model.id:
            with self._lock:
                self._models[(provider, model.id)] = model

    def remove_provider(self, provider: str) -> None:
        with self._lock:
            for key in [key for key in self._models if key[0] == provider]:
                del self._models[key]

    def get(self, provider: str, model: str) -> Optional[ModelInfo]:
        with self._lock:
            return self._models.get((provider, model))

    def capabilities(self, provider: str, model: str) -> ModelCapabilities:
        entry = self.get(provider, model)
        return entry.capabilities or ModelCapabilities() if entry else ModelCapabilities()

    def models_for_provider(self, provider: str) -> List[ModelInfo]:
        with self._lock:
            return [m for (name, _), m in self._models.items() if name == provider]

    def providers_for_capability(self, capability: str) -> List[str]:
        with self._lock:
            return sorted({
                provider for (provider, _), model in self._models.items()
                if (model.capabilities or ModelCapabilities()).supports(capability)
            })

    def snapshot(self) -> Dict[Tuple[str, str], ModelInfo]:
        with self._lock:
            return dict(self._models)

    def clear(self) -> None:
        with self._lock:
            self._models.clear()
