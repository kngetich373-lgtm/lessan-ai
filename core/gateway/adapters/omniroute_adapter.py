"""OmniRoute gateway adapter."""

from typing import Any, AsyncIterator, Dict, List, Optional

from core.gateway.adapters.base_adapter import BaseGatewayAdapter
from core.gateway.models import (
    GatewayCapabilities,
    GatewayConfig,
    GatewayMetrics,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    ModelRecord,
    ProviderRecord,
)
from core.logging import get_logger

logger = get_logger("OmniRouteAdapter")


class OmniRouteAdapter(BaseGatewayAdapter):
    """Adapter for the OmniRoute gateway."""

    gateway_type = "omniroute"

    def __init__(self) -> None:
        super().__init__()
        self._client: Any = None

    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        record = GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
        try:
            from omniroute import client as omniroute_client
            self._client = omniroute_client
            record.status = GatewayStatus.CONNECTED
            record.connected_at = __import__("datetime").datetime.now()
            logger.info(f"OmniRoute gateway '{config.gateway_id}' connected.")
        except Exception as exc:
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            logger.error(f"OmniRoute connect failed: {exc}")
        return record

    async def disconnect(self, record: GatewayRecord) -> None:
        self._client = None
        record.status = GatewayStatus.DISCONNECTED
        record.adapter = None
        logger.info(f"OmniRoute gateway '{record.config.gateway_id}' disconnected.")

    async def authenticate(self, record: GatewayRecord) -> bool:
        return self._client is not None

    async def health(self, record: GatewayRecord) -> GatewayRecord:
        if self._client is None:
            record.status = GatewayStatus.ERROR
            record.last_error = "No client"
            return record
        try:
            self._client.chat("ping")
            record.status = GatewayStatus.CONNECTED
            record.consecutive_failures = 0
            record.consecutive_successes += 1
        except Exception as exc:
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            record.consecutive_failures += 1
            record.consecutive_successes = 0
        return record

    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        return [self._default_provider(record)]

    async def list_providers(self, record: GatewayRecord) -> List[ProviderRecord]:
        return [self._default_provider(record)]

    async def provider_details(
        self, record: GatewayRecord, provider_id: str
    ) -> Optional[ProviderRecord]:
        return self._default_provider(record)

    def _default_provider(self, record: GatewayRecord) -> ProviderRecord:
        return ProviderRecord(
            provider_id="omniroute",
            gateway_id=record.config.gateway_id,
            name="OmniRoute",
            capabilities=GatewayCapabilities(
                streaming=True, tools=True, reasoning=True, extra={"free": True}
            ),
            supports_streaming=True,
            supports_tool_calling=True,
            is_local=False,
        )

    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        import time
        started = time.monotonic()
        try:
            text = self._client.chat(request.prompt)
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, True, latency)
            return GatewayResponse(
                text=text,
                provider="omniroute",
                gateway=record.config.gateway_id,
                success=True,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, False, latency)
            return GatewayResponse(
                text="",
                provider="omniroute",
                gateway=record.config.gateway_id,
                error=str(exc),
                success=False,
                latency_ms=latency,
            )

    async def stream_chat(
        self, record: GatewayRecord, request: GatewayRequest
    ) -> AsyncIterator[GatewayResponse]:
        raise NotImplementedError("OmniRoute streaming not yet implemented.")

    async def embeddings(
        self, record: GatewayRecord, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        raise NotImplementedError("OmniRoute embeddings not yet implemented.")

    async def image_generation(
        self, record: GatewayRecord, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError("OmniRoute image generation not yet implemented.")

    async def speech(
        self, record: GatewayRecord, text: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError("OmniRoute speech not yet implemented.")

    def supports_streaming(self, record: GatewayRecord) -> bool:
        return True

    def supports_tools(self, record: GatewayRecord) -> bool:
        return True

    def supports_reasoning(self, record: GatewayRecord) -> bool:
        return True
