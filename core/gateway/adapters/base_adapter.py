"""Base adapter for Gateway Hub gateway adapters."""

from typing import Any, AsyncIterator, Dict, List, Optional

from core.gateway.interfaces import BaseGatewayAdapter
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
from core.logging import get_logger


logger = get_logger("BaseGatewayAdapter")


class BaseGatewayAdapter(BaseGatewayAdapter):
    """Shared base for all concrete gateway adapters.

    Provides common plumbing (metrics, default capability stubs) so
    subclasses only need to implement the actual API integration.
    """

    gateway_type: str = "base"

    def __init__(self) -> None:
        self._metrics: Dict[str, GatewayMetrics] = {}

    def _metrics_for(self, gateway_id: str) -> GatewayMetrics:
        if gateway_id not in self._metrics:
            self._metrics[gateway_id] = GatewayMetrics(gateway_id=gateway_id)
        return self._metrics[gateway_id]

    async def _record_request(
        self,
        gateway_id: str,
        success: bool,
        latency_ms: float,
        tokens: int = 0,
    ) -> None:
        metrics = self._metrics_for(gateway_id)
        metrics.record_request(success, latency_ms, tokens)

    # Default capability stubs — override in subclasses when needed.
    def supports_streaming(self, record: GatewayRecord) -> bool:
        return False

    def supports_tools(self, record: GatewayRecord) -> bool:
        return False

    def supports_reasoning(self, record: GatewayRecord) -> bool:
        return False

    def supports_audio(self, record: GatewayRecord) -> bool:
        return False

    def supports_images(self, record: GatewayRecord) -> bool:
        return False

    def supports_video(self, record: GatewayRecord) -> bool:
        return False

    def supports_embeddings(self, record: GatewayRecord) -> bool:
        return False

    # Convenience stubs for capabilities that some gateways may not expose.
    async def embeddings(
        self, record: GatewayRecord, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        raise NotImplementedError(
            f"{self.gateway_type}.embeddings() is not supported."
        )

    async def image_generation(
        self, record: GatewayRecord, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError(
            f"{self.gateway_type}.image_generation() is not supported."
        )

    async def speech(
        self, record: GatewayRecord, text: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError(
            f"{self.gateway_type}.speech() is not supported."
        )
