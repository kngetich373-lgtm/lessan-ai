"""Data models used by the Model Router subsystem.

These are pure, provider-agnostic value objects. Providers advertise their
capabilities and costs through these models so the router can make decisions
without knowing anything about a specific vendor's API.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Set


class ProviderStatus(Enum):
    """Health status of a provider as tracked by the health monitor."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# Capability keys recognised by the router. Providers may add extra
# capability keys via ``ModelCapabilities.extra``; the router treats them
# as opaque but queryable flags.
CAPABILITY_TEXT = "text"
CAPABILITY_STREAMING = "streaming"
CAPABILITY_VISION = "vision"
CAPABILITY_TOOL_CALLING = "tool_calling"
CAPABILITY_EMBEDDINGS = "embeddings"
CAPABILITY_AUDIO = "audio"
CAPABILITY_IMAGE_GENERATION = "image_generation"
CAPABILITY_MULTILINGUAL = "multilingual"


@dataclass
class ModelCapabilities:
    """Capabilities a model/provider supports."""

    streaming: bool = False
    vision: bool = False
    tool_calling: bool = False
    embeddings: bool = False
    audio: bool = False
    image_generation: bool = False
    multilingual: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    def supports(self, capability: str) -> bool:
        """Return True if this capability set covers ``capability``."""
        key = capability.lower().strip()
        if key == CAPABILITY_TEXT:
            return True  # every model can produce text
        if key == CAPABILITY_STREAMING:
            return self.streaming
        if key == CAPABILITY_VISION:
            return self.vision
        if key == CAPABILITY_TOOL_CALLING:
            return self.tool_calling
        if key == CAPABILITY_EMBEDDINGS:
            return self.embeddings
        if key == CAPABILITY_AUDIO:
            return self.audio
        if key == CAPABILITY_IMAGE_GENERATION:
            return self.image_generation
        if key == CAPABILITY_MULTILINGUAL:
            return self.multilingual
        return bool(self.extra.get(key, False))

    def as_dict(self) -> Dict[str, Any]:
        data = {
            "streaming": self.streaming,
            "vision": self.vision,
            "tool_calling": self.tool_calling,
            "embeddings": self.embeddings,
            "audio": self.audio,
            "image_generation": self.image_generation,
            "multilingual": self.multilingual,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ModelCapabilities":
        data = data or {}
        known = {
            "streaming", "vision", "tool_calling", "embeddings",
            "audio", "image_generation", "multilingual",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(**{k: v for k, v in data.items() if k in known}, extra=extra)


@dataclass
class CostMetadata:
    """Cost information for a provider/model in a given currency."""

    currency: str = "USD"
    input_per_million: float = 0.0
    output_per_million: float = 0.0
    is_free: bool = False
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of a request in the provider's currency."""
        if self.is_free:
            return 0.0
        return (
            (self.input_per_million * input_tokens)
            + (self.output_per_million * output_tokens)
        ) / 1_000_000.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "input_per_million": self.input_per_million,
            "output_per_million": self.output_per_million,
            "is_free": self.is_free,
            "notes": self.notes,
        }


@dataclass
class ModelInfo:
    """A single model advertised by a provider."""

    id: str
    context_length: int = 0
    capabilities: Optional[ModelCapabilities] = None
    cost: Optional[CostMetadata] = None
    max_output_tokens: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "context_length": self.context_length,
            "capabilities": self.capabilities.as_dict() if self.capabilities else {},
            "cost": self.cost.as_dict() if self.cost else None,
            "max_output_tokens": self.max_output_tokens,
            "extra": self.extra,
        }


@dataclass
class ProviderHealth:
    """Runtime health snapshot for a provider."""

    status: ProviderStatus = ProviderStatus.UNKNOWN
    latency_ms: Optional[float] = None
    last_checked: Optional[datetime] = None
    error: Optional[str] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    @property
    def is_healthy(self) -> bool:
        return self.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "error": self.error,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
        }


@dataclass
class ProviderInfo:
    """Everything the router knows about a provider.

    @note Priority is a lower-is-better integer. 0 = highest priority.
    """

    name: str
    models: List[ModelInfo] = field(default_factory=list)
    capabilities: Optional[ModelCapabilities] = None
    context_length: int = 0
    supports_streaming: bool = False
    supports_vision: bool = False
    supports_tool_calling: bool = False
    cost: Optional[CostMetadata] = None
    priority: int = 100
    is_local: bool = False
    availability: ProviderStatus = ProviderStatus.UNKNOWN
    extra: Dict[str, Any] = field(default_factory=dict)

    def primary_capabilities(self) -> ModelCapabilities:
        """Return the provider-level capability set."""
        caps = self.capabilities or ModelCapabilities()
        return ModelCapabilities(
            streaming=self.supports_streaming or caps.streaming,
            vision=self.supports_vision or caps.vision,
            tool_calling=self.supports_tool_calling or caps.tool_calling,
            embeddings=caps.embeddings,
            audio=caps.audio,
            image_generation=caps.image_generation,
            multilingual=caps.multilingual,
            extra=dict(caps.extra),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "models": [m.as_dict() for m in self.models],
            "capabilities": self.primary_capabilities().as_dict(),
            "context_length": self.context_length,
            "supports_streaming": self.supports_streaming,
            "supports_vision": self.supports_vision,
            "supports_tool_calling": self.supports_tool_calling,
            "cost": self.cost.as_dict() if self.cost else None,
            "priority": self.priority,
            "is_local": self.is_local,
            "availability": self.availability.value,
        }


@dataclass
class RouteRequest:
    """A routing request submitted by the System Orchestrator or agents."""

    prompt: str
    system: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.7
    model: Optional[str] = None
    required_capabilities: List[str] = field(default_factory=list)
    preferred_provider: Optional[str] = None
    preferred_models: Optional[List[str]] = None
    max_cost: Optional[float] = None
    stream: bool = False
    context_estimate: Optional[int] = None
    timeout: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    """The outcome of a routing decision."""

    provider: str
    model: str
    score: float = 0.0
    reason: str = ""
    cost_estimate: Optional[float] = None
    latency_ms: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "score": self.score,
            "reason": self.reason,
            "cost_estimate": self.cost_estimate,
            "latency_ms": self.latency_ms,
        }


@dataclass
class RouteResult:
    """The full result of routing + executing a request."""

    request: RouteRequest
    provider: str
    model: str
    text: str = ""
    stream: Optional[Iterator[str]] = None
    cost: float = 0.0
    latency_ms: Optional[float] = None
    fallback_chain: List[str] = field(default_factory=list)
    error: Optional[str] = None
    success: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "fallback_chain": list(self.fallback_chain),
            "error": self.error,
            "success": self.success,
        }