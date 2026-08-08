"""Anthropic gateway adapter — Anthropic Messages API.

Anthropic's API differs from OpenAI-compatible APIs.  This adapter
normalizes Anthropic ``messages`` requests into the Gateway Hub's
abstract ``GatewayRequest`` / ``GatewayResponse`` schema.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.gateway.adapters.base_adapter import BaseGatewayAdapter
from core.gateway.models import (
    GatewayCapabilities,
    GatewayConfig,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    ModelRecord,
    ProviderRecord,
)
from core.logging import get_logger

logger = get_logger("AnthropicAdapter")

_ANTHROPIC_BASE = "https://api.anthropic.com"


class AnthropicAdapter(BaseGatewayAdapter):
    """Adapter for the Anthropic Messages API."""

    gateway_type = "anthropic"
    _DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, timeout: float = 60.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    def _api_key(self, record: GatewayRecord) -> str:
        return record.config.api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        record = GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
        key = config.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            config.api_key = key
            record.status = GatewayStatus.CONNECTED
            record.connected_at = __import__("datetime").datetime.now()
        else:
            record.status = GatewayStatus.ERROR
            record.last_error = "Anthropic API key is required."
        return record

    async def disconnect(self, record: GatewayRecord) -> None:
        await self._client.aclose()
        record.status = GatewayStatus.DISCONNECTED

    async def authenticate(self, record: GatewayRecord) -> bool:
        return bool(self._api_key(record))

    async def health(self, record: GatewayRecord) -> GatewayRecord:
        try:
            resp = await self._client.get(
                f"{_ANTHROPIC_BASE}/v1/models",
                headers={"x-api-key": self._api_key(record), "anthropic-version": "2023-06-01"},
                timeout=5.0,
            )
            if resp.status_code == 200:
                record.status = GatewayStatus.CONNECTED
                record.consecutive_failures = 0
                record.consecutive_successes += 1
            else:
                record.status = GatewayStatus.ERROR
                record.last_error = f"HTTP {resp.status_code}"
                record.consecutive_failures += 1
        except Exception as exc:  # noqa: BLE001
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            record.consecutive_failures += 1
        return record

    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        models: List[ModelRecord] = []
        try:
            resp = await self._client.get(
                f"{_ANTHROPIC_BASE}/v1/models",
                headers={"x-api-key": self._api_key(record), "anthropic-version": "2023-06-01"},
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    models.append(ModelRecord(
                        model_id=m.get("id", ""),
                        provider_id="anthropic",
                        gateway_id=record.config.gateway_id,
                        name=m.get("display_name", m.get("id", "")),
                        context_length=m.get("context_window", 0),
                        capabilities=GatewayCapabilities(streaming=True, tools=True, reasoning=True),
                    ))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Anthropic discovery failed: {exc}")
        return [
            ProviderRecord(
                provider_id="anthropic",
                gateway_id=record.config.gateway_id,
                name="Anthropic",
                models=models,
                capabilities=GatewayCapabilities(streaming=True, tools=True, reasoning=True),
                supports_streaming=True,
                supports_tool_calling=True,
                is_local=False,
            )
        ]

    async def list_providers(self, record: GatewayRecord) -> List[ProviderRecord]:
        return await self.discover(record)

    async def provider_details(self, record, provider_id: str) -> Optional[ProviderRecord]:
        for p in await self.discover(record):
            if p.provider_id == provider_id:
                return p
        return None

    def _build_payload(self, request: GatewayRequest) -> dict:
        messages: List[Dict[str, Any]] = []
        if request.system:
            messages.append({"role": "user", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: Dict[str, Any] = {
            "model": request.model or self._DEFAULT_MODEL,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature or 0.7,
            "stream": request.stream,
        }
        return payload

    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        started = time.monotonic()
        model = request.model or self._DEFAULT_MODEL
        payload = self._build_payload(request)
        headers = {
            "x-api-key": self._api_key(record),
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            resp = await self._client.post(
                f"{_ANTHROPIC_BASE}/v1/messages", json=payload, headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(
                record.config.gateway_id, True, latency,
                input_tokens + output_tokens,
            )
            return GatewayResponse(
                text=text,
                model=model,
                provider="anthropic",
                gateway=record.config.gateway_id,
                success=True,
                latency_ms=latency,
                tokens_used=input_tokens + output_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, False, latency)
            return GatewayResponse(
                text="", model=model, provider="anthropic",
                gateway=record.config.gateway_id, error=str(exc),
                success=False, latency_ms=latency,
            )

    async def stream_chat(self, record, request):
        model = request.model or self._DEFAULT_MODEL
        payload = self._build_payload(request)
        headers = {
            "x-api-key": self._api_key(record),
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "accept": "text/event-stream",
        }
        try:
            async with self._client.stream(
                "POST", f"{_ANTHROPIC_BASE}/v1/messages",
                json=payload, headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[6:].strip()
                    if not data:
                        continue
                    try:
                        chunk = json.loads(data)
                        if chunk.get("type") == "content_block_delta":
                            text = chunk.get("delta", {}).get("text", "")
                            if text:
                                yield GatewayResponse(
                                    text=text, model=model, provider="anthropic",
                                    gateway=record.config.gateway_id, success=True,
                                )
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as exc:  # noqa: BLE001
            yield GatewayResponse(
                text="", model=model, provider="anthropic",
                gateway=record.config.gateway_id, error=str(exc),
                success=False,
            )

    async def embeddings(self, record, texts, model=None):
        raise NotImplementedError("Anthropic embeddings not yet implemented.")

    def supports_streaming(self, record) -> bool:
        return True

    def supports_tools(self, record) -> bool:
        return True

    def supports_reasoning(self, record) -> bool:
        return True