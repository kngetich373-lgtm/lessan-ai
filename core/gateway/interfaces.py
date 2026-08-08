"""Gateway adapter interface.

Every gateway adapter must implement this interface. The Gateway Hub
communicates with gateways exclusively through this contract, so the
Routing Engine never knows about specific gateway APIs.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from core.gateway.models import (
    GatewayCapabilities,
    GatewayConfig,
    GatewayMetrics,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    ModelRecord,
    ProviderRecord,
)


class BaseGatewayAdapter(ABC):
    """Interface every gateway adapter must implement.

    Adapters translate between the Gateway Hub's abstract interface and
    each gateway's actual API. They must never leak gateway-specific
    details outside the adapter itself.
    """

    gateway_type: str = "base"

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        """Establish connection to the gateway.

        Returns a GatewayRecord reflecting the new connection state.
        """

    @abstractmethod
    async def disconnect(self, record: GatewayRecord) -> None:
        """Tear down the gateway connection."""

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def authenticate(self, record: GatewayRecord) -> bool:
        """Verify credentials with the gateway.

        Returns True when authentication succeeds.
        """

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def health(self, record: GatewayRecord) -> GatewayRecord:
        """Probe the gateway and return the updated record."""

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        """Discover providers and models from the gateway.

        Returns a list of ProviderRecord objects describing everything
        the gateway can serve.
        """

    @abstractmethod
    async def list_providers(self, record: GatewayRecord) -> List[ProviderRecord]:
        """List all providers currently known to this gateway."""

    @abstractmethod
    async def provider_details(
        self, record: GatewayRecord, provider_id: str
    ) -> Optional[ProviderRecord]:
        """Return full details for a single provider."""

    # ------------------------------------------------------------------ #
    # Invocation
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        """Execute a non-streaming chat completion."""

    @abstractmethod
    async def stream_chat(
        self, record: GatewayRecord, request: GatewayRequest
    ) -> AsyncIterator[GatewayResponse]:
        """Execute a streaming chat completion, yielding chunks."""

    @abstractmethod
    async def embeddings(
        self, record: GatewayRecord, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings for the given texts."""

    @abstractmethod
    async def image_generation(
        self, record: GatewayRecord, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        """Generate an image from a text prompt."""

    @abstractmethod
    async def speech(
        self, record: GatewayRecord, text: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        """Synthesize speech from text."""

    # ------------------------------------------------------------------ #
    # Capability queries
    # ------------------------------------------------------------------ #
    @abstractmethod
    def supports_streaming(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports streaming."""

    @abstractmethod
    def supports_tools(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports tool/function calling."""

    @abstractmethod
    def supports_reasoning(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports extended reasoning."""

    @abstractmethod
    def supports_audio(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports audio input/output."""

    @abstractmethod
    def supports_images(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports image input."""

    @abstractmethod
    def supports_video(self, record: GatewayRecord) -> bool:
        """Whether this gateway supports video input."""

    @abstractmethod
    def supports_embeddings(self, record: GatewayRecord) -> bool:
        """Whether this gateway exposes an embeddings endpoint."""
