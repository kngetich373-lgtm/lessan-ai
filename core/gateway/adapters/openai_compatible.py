"""OpenAI-compatible gateway adapter base.

Most LLM gateways (OpenAI, DeepSeek, OpenRouter, Kimi, vLLM, LM Studio,
LiteLLM, Ollama v1, and custom OpenAI-compatible endpoints) expose an
OpenAI-style ``/chat/completions`` and ``/models`` endpoint. This module
provides a fully-implemented base adapter so each concrete adapter only
needs to set its ``gateway_type`` and ``_BASE_URL``.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

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

logger = get_logger("OpenAICompatibleAdapter")


class OpenAICompatibleAdapter(BaseGatewayAdapter):
    """
    Base adapter for any OpenAI-compatible chat-completions API.

    Subclasses set ``gateway_type`` and ``_BASE_URL``. All chat, streaming,
    discovery, health-check, and capability logic is inherited.
    """

    gateway_type: str = "openai_compatible"
    _BASE_URL: str = "https://api.openai.com/v1"

    # Default model used when the caller does not specify one.
    _DEFAULT_MODEL: str = "gpt-4o-mini"

    def __init__(self, timeout: float = 60.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    # ------------------------------------------------------------------ #
    # Helper: build auth header
    # ------------------------------------------------------------------ #
    def _auth_headers(self, record: GatewayRecord) -> Dict[str, str]:
        key = record.config.api_key or os.environ.get(self._env_key_name(), "")
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _env_key_name(self) -> str:
        """
        Environment variable that holds the API key for this gateway type.
        Subclasses may override; default is ``<GATEWAY_TYPE>_API_KEY`` upper-cased.
        """
        return f"{self.gateway_type.upper()}_API_KEY"

    def _resolve_base_url(self, record: GatewayRecord) -> str:
        """Use the config's base_url if set, otherwise the adapter default."""
        return record.config.base_url or self._BASE_URL

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        record = GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
        try:
            key = config.api_key or os.environ.get(self._env_key_name(), "")
            if key:
                config.api_key = key
            record.status = GatewayStatus.CONNECTED
            record.connected_at = __import__("datetime").datetime.now()
            logger.info(f"{self.gateway_type} gateway '{config.gateway_id}' connected.")
        except Exception as exc:  # noqa: BLE001
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            logger.error(f"{self.gateway_type} connect failed: {exc}")
        return record

    async def disconnect(self, record: GatewayRecord) -> None:
        await self._client.aclose()
        record.status = GatewayStatus.DISCONNECTED
        logger.info(f"{self.gateway_type} gateway '{record.config.gateway_id}' disconnected.")

    async def authenticate(self, record: GatewayRecord) -> bool:
        try:
            resp = await self._client.get(
                f"{self._resolve_base_url(record)}/models",
                headers=self._auth_headers(record),
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def health(self, record: GatewayRecord) -> GatewayRecord:
        try:
            resp = await self._client.get(
                f"{self._resolve_base_url(record)}/models",
                headers=self._auth_headers(record),
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

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        models: List[ModelRecord] = []
        try:
            resp = await self._client.get(
                f"{self._resolve_base_url(record)}/models",
                headers=self._auth_headers(record),
            )
            if resp.status_code == 200:
                data = resp.json()
                model_list = (
                    data.get("data", [])
                    if isinstance(data, dict)
                    else data if isinstance(data, list) else []
                )
                for m in model_list:
                    if isinstance(m, dict):
                        models.append(self._model_from_api(m))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"{self.gateway_type} discovery failed: {exc}")
        return [
            ProviderRecord(
                provider_id=self.gateway_type,
                gateway_id=record.config.gateway_id,
                name=self.gateway_type,
                models=models,
                capabilities=GatewayCapabilities(
                    streaming=True, tools=True, reasoning=True,
                ),
                supports_streaming=True,
                supports_tool_calling=True,
                is_local=record.config.base_url.startswith("http://127.")
                or record.config.base_url.startswith("http://localhost"),
            )
        ]

    async def list_providers(self, record: GatewayRecord) -> List[ProviderRecord]:
        return await self.discover(record)

    async def provider_details(
        self, record: GatewayRecord, provider_id: str
    ) -> Optional[ProviderRecord]:
        providers = await self.discover(record)
        for p in providers:
            if p.provider_id == provider_id:
                return p
        return None

    def _model_from_api(self, m: dict) -> ModelRecord:
        return ModelRecord(
            model_id=m.get("id", ""),
            provider_id=self.gateway_type,
            gateway_id="",
            name=m.get("id", ""),
            context_length=m.get("context_length", 0) or m.get("context_length", 0),
            capabilities=GatewayCapabilities(
                streaming=True,
                tools=m.get("supported_parameters", {}).get("tools", False)
                if isinstance(m.get("supported_parameters"), dict)
                else True,
            ),
        )

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    def _build_payload(self, request: GatewayRequest) -> dict:
        messages: List[Dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: Dict[str, Any] = {
            "model": request.model or self._DEFAULT_MODEL,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        return payload

    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        started = time.monotonic()
        model = request.model or self._DEFAULT_MODEL
        payload = self._build_payload(request)
        try:
            resp = await self._client.post(
                f"{self._resolve_base_url(record)}/chat/completions",
                json=payload,
                headers=self._auth_headers(record),
            )
            resp.raise_for_status()
            data = resp.json()
            text = ""
            if data.get("choices"):
                msg = data["choices"][0].get("message", {})
                if "content" in msg:
                    text = msg["content"]
            usage = data.get("usage", {})
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(
                record.config.gateway_id, True, latency,
                usage.get("total_tokens", 0),
            )
            return GatewayResponse(
                text=text,
                model=model,
                provider=self.gateway_type,
                gateway=record.config.gateway_id,
                success=True,
                latency_ms=latency,
                tokens_used=usage.get("total_tokens", 0),
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, False, latency)
            return GatewayResponse(
                text="",
                model=model,
                provider=self.gateway_type,
                gateway=record.config.gateway_id,
                error=str(exc),
                success=False,
                latency_ms=latency,
            )

    async def stream_chat(
        self, record: GatewayRecord, request: GatewayRequest
    ) -> AsyncIterator[GatewayResponse]:
        model = request.model or self._DEFAULT_MODEL
        payload = self._build_payload(request)
        payload["stream"] = True
        started = time.monotonic()
        try:
            async with self._client.stream(
                "POST",
                f"{self._resolve_base_url(record)}/chat/completions",
                json=payload,
                headers=self._auth_headers(record),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if chunk.get("choices"):
                            delta = chunk["choices"][0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield GatewayResponse(
                                    text=text,
                                    model=model,
                                    provider=self.gateway_type,
                                    gateway=record.config.gateway_id,
                                    success=True,
                                    latency_ms=(time.monotonic() - started) * 1000.0,
                                )
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as exc:  # noqa: BLE001
            yield GatewayResponse(
                text="",
                model=model,
                provider=self.gateway_type,
                gateway=record.config.gateway_id,
                error=str(exc),
                success=False,
            )

    async def embeddings(
        self, record: GatewayRecord, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        try:
            resp = await self._client.post(
                f"{self._resolve_base_url(record)}/embeddings",
                json={"model": model or "text-embedding-3-small", "input": texts},
                headers=self._auth_headers(record),
            )
            resp.raise_for_status()
            data = resp.json()
            return [e["embedding"] for e in data.get("data", [])]
        except Exception as exc:  # noqa: BLE001
            logger.error(f"{self.gateway_type} embeddings failed: {exc}")
            return []

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    def supports_streaming(self, record: GatewayRecord) -> bool:
        return True

    def supports_tools(self, record: GatewayRecord) -> bool:
        return True

    def supports_reasoning(self, record: GatewayRecord) -> bool:
        return True

    def supports_images(self, record: GatewayRecord) -> bool:
        return False

    def supports_embeddings(self, record: GatewayRecord) -> bool:
        return True
