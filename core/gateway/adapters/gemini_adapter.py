"""Gemini gateway adapter — Google Gemini REST API.

Uses the Gemini REST endpoint directly (no SDK dependency required).
Gemini's API differs from OpenAI-compatible APIs, so this adapter
normalizes ``GatewayRequest`` / ``GatewayResponse`` to and from the
Gemini ``contents`` schema.
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

logger = get_logger("GeminiAdapter")

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAdapter(BaseGatewayAdapter):
    """Adapter for Google Gemini via REST API."""

    gateway_type = "gemini"
    _DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, timeout: float = 60.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    def _api_key(self, record: GatewayRecord) -> str:
        return record.config.api_key or os.environ.get("GOOGLE_API_KEY", "")

    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        record = GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
        key = config.api_key or os.environ.get("GOOGLE_API_KEY", "")
        if key:
            config.api_key = key
            record.status = GatewayStatus.CONNECTED
            record.connected_at = __import__("datetime").datetime.now()
            logger.info(f"Gemini gateway '{config.gateway_id}' connected.")
        else:
            record.status = GatewayStatus.ERROR
            record.last_error = "Google API key is required."
            logger.error("Gemini connect failed: no API key.")
        return record

    async def disconnect(self, record: GatewayRecord) -> None:
        await self._client.aclose()
        record.status = GatewayStatus.DISCONNECTED
        logger.info(f"Gemini gateway '{record.config.gateway_id}' disconnected.")

    async def authenticate(self, record: GatewayRecord) -> bool:
        key = self._api_key(record)
        if not key:
            return False
        try:
            resp = await self._client.get(
                f"{_GEMINI_BASE}/models?key={key}",
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def health(self, record: GatewayRecord) -> GatewayRecord:
        try:
            resp = await self._client.get(
                f"{_GEMINI_BASE}/models?key={self._api_key(record)}",
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
            record.consecutive_successes = 0
        return record

    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        models: List[ModelRecord] = []
        try:
            resp = await self._client.get(
                f"{_GEMINI_BASE}/models?key={self._api_key(record)}",
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("models", []):
                    mid = m.get("name", "").replace("models/", "")
                    if mid:
                        models.append(ModelRecord(
                            model_id=mid,
                            provider_id="gemini",
                            gateway_id=record.config.gateway_id,
                            name=mid,
                            context_length=m.get("inputTokenLimit", 0),
                            capabilities=GatewayCapabilities(
                                streaming=True, tools=True, reasoning=True,
                            ),
                        ))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Gemini discovery failed: {exc}")
        return [
            ProviderRecord(
                provider_id="gemini",
                gateway_id=record.config.gateway_id,
                name="Gemini",
                models=models,
                capabilities=GatewayCapabilities(
                    streaming=True, tools=True, reasoning=True,
                    images=True, audio=True,
                ),
                supports_streaming=True,
                supports_tool_calling=True,
                is_local=False,
            )
        ]

    async def list_providers(self, record: GatewayRecord) -> List[ProviderRecord]:
        return await self.discover(record)

    async def provider_details(self, record: GatewayRecord, provider_id: str) -> Optional[ProviderRecord]:
        for p in await self.discover(record):
            if p.provider_id == provider_id:
                return p
        return None

    def _build_payload(self, request: GatewayRequest) -> dict:
        contents: List[Dict[str, Any]] = []
        if request.system:
            contents.append({"role": "user", "parts": [{"text": request.system}]})
        contents.append({"role": "user", "parts": [{"text": request.prompt}]})
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        return payload

    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        started = time.monotonic()
        model = request.model or self._DEFAULT_MODEL
        payload = self._build_payload(request)
        try:
            url = f"{_GEMINI_BASE}/models/{model}:generateContent?key={self._api_key(record)}"
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = ""
            candidates = data.get("candidates", [])
            if candidates and candidates[0].get("content", {}).get("parts"):
                for part in candidates[0]["content"]["parts"]:
                    text += part.get("text", "")
            usage = data.get("usageMetadata", {})
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(
                record.config.gateway_id, True, latency,
                usage.get("totalTokenCount", 0),
            )
            return GatewayResponse(
                text=text,
                model=model,
                provider="gemini",
                gateway=record.config.gateway_id,
                success=True,
                latency_ms=latency,
                tokens_used=usage.get("totalTokenCount", 0),
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, False, latency)
            return GatewayResponse(
                text="", model=model, provider="gemini",
                gateway=record.config.gateway_id, error=str(exc),
                success=False, latency_ms=latency,
            )

    async def stream_chat(self, record: GatewayRecord, request: GatewayRequest):
        # Gemini streaming uses a different endpoint; fall back to non-stream
        resp = await self.chat(record, request)
        yield resp

    async def embeddings(self, record: GatewayRecord, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        raise NotImplementedError("Gemini embeddings not yet implemented.")

    def supports_streaming(self, record: GatewayRecord) -> bool:
        return True

    def supports_tools(self, record: GatewayRecord) -> bool:
        return True

    def supports_reasoning(self, record: GatewayRecord) -> bool:
        return True

    def supports_images(self, record: GatewayRecord) -> bool:
        return True

    def supports_audio(self, record: GatewayRecord) -> bool:
        return True