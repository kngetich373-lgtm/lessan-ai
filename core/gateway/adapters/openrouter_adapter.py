"""OpenRouter gateway adapter."""

import os
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

logger = get_logger("OpenRouterAdapter")


class OpenRouterAdapter(BaseGatewayAdapter):
    """Adapter for the OpenRouter gateway."""

    gateway_type = "openrouter"
    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def connect(self, config: GatewayConfig) -> GatewayRecord:
        record = GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
        try:
            if not config.api_key:
                config.api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not config.api_key:
                raise ValueError("OpenRouter API key is required.")
            record.status = GatewayStatus.CONNECTED
            record.connected_at = __import__("datetime").datetime.now()
            logger.info(f"OpenRouter gateway '{config.gateway_id}' connected.")
        except Exception as exc:
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            logger.error(f"OpenRouter connect failed: {exc}")
        return record

    async def disconnect(self, record: GatewayRecord) -> None:
        await self._client.aclose()
        record.status = GatewayStatus.DISCONNECTED
        logger.info(f"OpenRouter gateway '{record.config.gateway_id}' disconnected.")

    async def authenticate(self, record: GatewayRecord) -> bool:
        try:
            resp = await self._client.get(
                f"{self._BASE_URL}/auth/key",
                headers={"Authorization": f"Bearer {record.config.api_key}"},
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def health(self, record: GatewayRecord) -> GatewayRecord:
        try:
            resp = await self._client.get(
                f"{self._BASE_URL}/models",
                headers={"Authorization": f"Bearer {record.config.api_key}"},
                timeout=5.0,
            )
            record.status = GatewayStatus.CONNECTED if resp.status_code == 200 else GatewayStatus.ERROR
            record.consecutive_failures = 0 if resp.status_code == 200 else record.consecutive_failures + 1
        except Exception as exc:
            record.status = GatewayStatus.ERROR
            record.last_error = str(exc)
            record.consecutive_failures += 1
        return record

    async def discover(self, record: GatewayRecord) -> List[ProviderRecord]:
        providers = []
        try:
            resp = await self._client.get(
                f"{self._BASE_URL}/models",
                headers={"Authorization": f"Bearer {record.config.api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                model_list = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                models = []
                for m in model_list:
                    if not isinstance(m, dict):
                        continue
                    models.append(ModelRecord(
                        model_id=m.get("id", ""),
                        provider_id="openrouter",
                        gateway_id=record.config.gateway_id,
                        name=m.get("name", m.get("id", "")),
                        context_length=m.get("context_length", 0),
                        capabilities=GatewayCapabilities(
                            streaming=True,
                            tools=m.get("supported_parameters", {}).get("tools", False)
                            if isinstance(m.get("supported_parameters"), dict)
                            else True,
                            reasoning="reasoning" in m.get("id", "").lower(),
                        ),
                    ))
                providers.append(ProviderRecord(
                    provider_id="openrouter",
                    gateway_id=record.config.gateway_id,
                    name="OpenRouter",
                    models=models,
                    capabilities=GatewayCapabilities(streaming=True, tools=True, reasoning=True),
                    supports_streaming=True,
                    supports_tool_calling=True,
                ))
        except Exception as exc:
            logger.error(f"OpenRouter discovery failed: {exc}")
        return providers

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

    async def chat(self, record: GatewayRecord, request: GatewayRequest) -> GatewayResponse:
        import time
        started = time.monotonic()
        model = request.model or "openai/gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.system:
            payload["messages"].insert(0, {"role": "system", "content": request.system})
        try:
            resp = await self._client.post(
                f"{self._BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {record.config.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(
                record.config.gateway_id, True, latency,
                usage.get("total_tokens", 0),
            )
            return GatewayResponse(
                text=text,
                model=model,
                provider="openrouter",
                gateway=record.config.gateway_id,
                success=True,
                latency_ms=latency,
                tokens_used=usage.get("total_tokens", 0),
            )
        except Exception as exc:
            latency = (time.monotonic() - started) * 1000.0
            await self._record_request(record.config.gateway_id, False, latency)
            return GatewayResponse(
                text="",
                model=model,
                provider="openrouter",
                gateway=record.config.gateway_id,
                error=str(exc),
                success=False,
                latency_ms=latency,
            )

    async def stream_chat(
        self, record: GatewayRecord, request: GatewayRequest
    ) -> AsyncIterator[GatewayResponse]:
        model = request.model or "openai/gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.system:
            payload["messages"].insert(0, {"role": "system", "content": request.system})
        async with self._client.stream(
            "POST",
            f"{self._BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {record.config.api_key}"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        text = chunk["choices"][0].get("delta", {}).get("content", "")
                        if text:
                            yield GatewayResponse(
                                text=text,
                                model=model,
                                provider="openrouter",
                                gateway=record.config.gateway_id,
                                success=True,
                            )
                    except Exception:
                        continue

    async def embeddings(
        self, record: GatewayRecord, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        raise NotImplementedError("OpenRouter embeddings via /embeddings endpoint.")

    async def image_generation(
        self, record: GatewayRecord, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError("OpenRouter image generation not yet implemented.")

    async def speech(
        self, record: GatewayRecord, text: str, model: Optional[str] = None, **kwargs: Any
    ) -> bytes:
        raise NotImplementedError("OpenRouter speech not yet implemented.")

    def supports_streaming(self, record: GatewayRecord) -> bool:
        return True

    def supports_tools(self, record: GatewayRecord) -> bool:
        return True

    def supports_reasoning(self, record: GatewayRecord) -> bool:
        return True
