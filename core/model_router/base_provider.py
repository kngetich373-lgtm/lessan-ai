"""Base provider interface for the Model Router.

Every AI provider adapter (Anthropic, OpenAI, Gemini, OpenRouter,
OmniRouter, Ollama, local models, ...) must implement this ABC. The router
relies *only* on this interface — it never contains provider-specific
logic, so new providers can be added without modifying the router.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

from core.model_router.models import ModelInfo, ProviderInfo, RouteRequest


class BaseModelProvider(ABC):
    """Interface each AI provider adapter must implement.

    Implementations are intentionally provider-agnostic on the outside and
    provider-specific only *inside* the adapter. The router drives providers
    exclusively through this contract.
    """

    # ------------------------------------------------------------------ #
    # Identity & discovery
    # ------------------------------------------------------------------ #
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name, e.g. ``"anthropic"``, ``"ollama"``."""

    @abstractmethod
    def available_models(self) -> List[ModelInfo]:
        """Return the list of models this provider can serve."""

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Return the provider-level capability flags.

        Keys are the CAPABILITY_* constants defined in
        :mod:`core.model_router.models` (e.g. ``"streaming"``,
        ``"vision"``, ``"tool_calling"``).
        """

    # ------------------------------------------------------------------ #
    # Provider information
    # ------------------------------------------------------------------ #
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return a fully-populated :class:`ProviderInfo` snapshot.

        The router uses this for scoring, filtering and reporting without
        ever calling into vendor-specific code.
        """

    # ------------------------------------------------------------------ #
    # Invocation
    # ------------------------------------------------------------------ #
    @abstractmethod
    def complete(self, request: RouteRequest) -> str:
        """Run a non-streaming completion and return the full text."""

    @abstractmethod
    def complete_stream(self, request: RouteRequest) -> Iterator[str]:
        """Run a streaming completion, yielding text chunks.

        Called only when :meth:`supports_streaming` is True.
        """

    # ------------------------------------------------------------------ #
    # Lifecycle / health
    # ------------------------------------------------------------------ #
    @abstractmethod
    def check_health(self) -> bool:
        """Perform a lightweight reachability check.

        Returns True if the provider is reachable and usable; False
        otherwise. The health monitor calls this on its own schedule.
        """

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return live status metadata (latency, model count, etc.)."""

    # ------------------------------------------------------------------ #
    # Convenience capability query (non-abstract, provided by the base)
    # ------------------------------------------------------------------ #
    @property
    def supports_streaming(self) -> bool:
        """Whether this provider advertises streaming support."""
        return bool(self.capabilities().get("streaming", False))

    @property
    def supports_vision(self) -> bool:
        """Whether this provider advertises vision support."""
        return bool(self.capabilities().get("vision", False))

    @property
    def supports_tool_calling(self) -> bool:
        """Whether this provider advertises tool calling."""
        return bool(self.capabilities().get("tool_calling", False))

    @property
    def is_local(self) -> bool:
        """Whether this provider runs locally (offline capable)."""
        return bool(self.capabilities().get("local", False))

    def to_registry_entry(self) -> ProviderInfo:
        """Build the ProviderInfo used for registration/serving."""
        return self.info()