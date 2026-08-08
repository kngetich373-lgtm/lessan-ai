"""Data models for the Gateway Hub subsystem."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class GatewayStatus(Enum):
    """Lifecycle state of a gateway connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"
    DISABLED = "disabled"


class GatewayType(Enum):
    """Supported gateway types."""

    OMNIRoute = "omniroute"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    KIMI = "kimi"
    LITELLM = "litellm"
    OLLAMA = "ollama"
    LM_STUDIO = "lmstudio"
    VLLM = "vllm"
    CUSTOM_OPENAI = "custom_openai"


@dataclass
class GatewayCapabilities:
    """Capabilities advertised by a gateway."""

    streaming: bool = False
    tools: bool = False
    reasoning: bool = False
    audio: bool = False
    images: bool = False
    video: bool = False
    embeddings: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: str) -> bool:
        key = capability.lower().strip()
        return getattr(self, key, False) or bool(self.extra.get(key, False))


@dataclass
class GatewayConfig:
    """Configuration for a single gateway connection."""

    gateway_id: str
    gateway_type: GatewayType
    name: str = ""
    display_name: str = ""
    enabled: bool = True
    priority: int = 100
    api_key: str = ""
    base_url: str = ""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    auto_reconnect: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.gateway_id
        if not self.display_name:
            self.display_name = self.gateway_type.value


@dataclass
class GatewayRecord:
    """Runtime state for a gateway connection."""

    config: GatewayConfig
    status: GatewayStatus = GatewayStatus.DISCONNECTED
    connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    adapter: Any = None

    @property
    def is_connected(self) -> bool:
        return self.status in (
            GatewayStatus.CONNECTED,
            GatewayStatus.AUTHENTICATED,
        )

    @property
    def is_healthy(self) -> bool:
        return self.status in (
            GatewayStatus.CONNECTED,
            GatewayStatus.AUTHENTICATED,
        ) and self.consecutive_failures == 0


@dataclass
class ProviderRecord:
    """A provider discovered from a connected gateway."""

    provider_id: str
    gateway_id: str
    name: str
    models: List["ModelRecord"] = field(default_factory=list)
    capabilities: GatewayCapabilities = field(default_factory=GatewayCapabilities)
    context_length: int = 0
    supports_streaming: bool = False
    supports_vision: bool = False
    supports_tool_calling: bool = False
    priority: int = 100
    is_local: bool = False
    cost: Optional["CostMetadata"] = None
    latency_ms: Optional[float] = None
    last_checked: Optional[datetime] = None
    status: str = "unknown"
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "models": [m.as_dict() for m in self.models],
            "capabilities": self.capabilities.extra,
            "context_length": self.context_length,
            "supports_streaming": self.supports_streaming,
            "supports_vision": self.supports_vision,
            "supports_tool_calling": self.supports_tool_calling,
            "priority": self.priority,
            "is_local": self.is_local,
            "cost": self.cost.as_dict() if self.cost else None,
            "latency_ms": self.latency_ms,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "status": self.status,
            "extra": self.extra,
        }


@dataclass
class ModelRecord:
    """A model advertised by a provider."""

    model_id: str
    provider_id: str
    gateway_id: str
    name: str = ""
    context_length: int = 0
    capabilities: GatewayCapabilities = field(default_factory=GatewayCapabilities)
    cost: Optional["CostMetadata"] = None
    max_output_tokens: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "context_length": self.context_length,
            "capabilities": self.capabilities.extra,
            "cost": self.cost.as_dict() if self.cost else None,
            "max_output_tokens": self.max_output_tokens,
            "extra": self.extra,
        }


@dataclass
class CostMetadata:
    """Cost information for a provider or model."""

    currency: str = "USD"
    input_per_million: float = 0.0
    output_per_million: float = 0.0
    is_free: bool = False
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "input_per_million": self.input_per_million,
            "output_per_million": self.output_per_million,
            "is_free": self.is_free,
            "notes": self.notes,
            "extra": self.extra,
        }


@dataclass
class GatewayHealth:
    """Health snapshot for a gateway."""

    gateway_id: str
    status: GatewayStatus
    latency_ms: Optional[float] = None
    last_checked: Optional[datetime] = None
    error: Optional[str] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    @property
    def is_healthy(self) -> bool:
        return self.status in (
            GatewayStatus.CONNECTED,
            GatewayStatus.AUTHENTICATED,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "error": self.error,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
        }


@dataclass
class GatewayMetrics:
    """Usage metrics for a gateway."""

    gateway_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    last_request_at: Optional[datetime] = None

    def record_request(self, success: bool, latency_ms: float, tokens: int = 0) -> None:
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        self.total_tokens += tokens
        self.total_latency_ms += latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.total_requests
        self.last_request_at = datetime.now()

    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def as_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate(),
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_request_at": self.last_request_at.isoformat() if self.last_request_at else None,
        }


@dataclass
class GatewayRequest:
    """A request routed through the Gateway Hub."""

    prompt: str
    system: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.7
    model: Optional[str] = None
    provider: Optional[str] = None
    gateway: Optional[str] = None
    stream: bool = False
    required_capabilities: List[str] = field(default_factory=list)
    context: Optional[str] = None
    timeout: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResponse:
    """Response from a gateway."""

    text: str = ""
    model: str = ""
    provider: str = ""
    gateway: str = ""
    stream: Optional[Any] = None
    tokens_used: int = 0
    latency_ms: Optional[float] = None
    finish_reason: str = ""
    error: Optional[str] = None
    success: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "gateway": self.gateway,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "error": self.error,
            "success": self.success,
            "extra": self.extra,
        }
