"""Cloud provider base classes and shared HTTP execution helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.logging import get_logger
from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import (
    CostMetadata,
    ModelCapabilities,
    ModelInfo,
    ProviderInfo,
    RouteRequest,
)

logger = get_logger("CloudProvider")


class CloudProviderBase(BaseModelProvider):
    """Common configuration, discovery and HTTP execution for cloud providers.

    Subclasses may set ``chat_api_style = "openai"`` when their completion
    endpoint follows the OpenAI chat-completions contract. Providers with a
    different protocol should implement ``complete`` and ``complete_stream``
    themselves rather than inheriting an incorrect transport.
    """

    provider_name: str = "cloud"
    display_name: str = "Cloud Provider"
    api_key_env: str = ""
    api_base: str = ""
    chat_api_style: Optional[str] = None
    default_models: List[Dict[str, Any]] = []
    default_capabilities: Dict[str, Any] = {}
    is_free_default: bool = False
    priority_default: int = 60
    context_length_default: int = 8192

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key
        self._discovered_models: Optional[List[ModelInfo]] = None

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key.strip() or None
        if self.api_key_env:
            return os.environ.get(self.api_key_env) or None
        return None

    def available_models(self) -> List[ModelInfo]:
        if self._discovered_models is not None:
            return list(self._discovered_models)
        return self._models_from_data(self.default_models)

    def discover_models(self) -> List[ModelInfo]:
        """Return a static catalogue unless a subclass provides discovery."""
        return self._models_from_data(self.default_models)

    def refresh_models(self) -> List[ModelInfo]:
        """Refresh models without allowing discovery failure to break startup."""
        try:
            discovered = self.discover_models()
            if discovered:
                self._discovered_models = discovered
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s model discovery failed: %s", self.provider_name, exc)
        return self.available_models()

    def _models_from_data(self, model_data_list: List[Dict[str, Any]]) -> List[ModelInfo]:
        models: List[ModelInfo] = []
        for model_data in model_data_list:
            model_id = model_data.get("id")
            if not model_id:
                continue
            extra = dict(model_data.get("extra", {}))
            models.append(
                ModelInfo(
                    id=model_id,
                    capabilities=ModelCapabilities(
                        streaming=model_data.get("streaming", True),
                        vision=model_data.get("vision", False),
                        tool_calling=model_data.get("tool_calling", True),
                        embeddings=model_data.get("embeddings", False),
                        audio=model_data.get("audio", False),
                        image_generation=model_data.get("image_generation", False),
                        extra=extra,
                    ),
                    context_length=model_data.get("context_length", self.context_length_default),
                    max_output_tokens=model_data.get("max_output_tokens", 0),
                    cost=CostMetadata(
                        input_per_million=model_data.get("input_per_million", 0.0),
                        output_per_million=model_data.get("output_per_million", 0.0),
                        is_free=extra.get("free", self.is_free_default),
                    ),
                    extra={
                        "name": model_data.get("name", model_id),
                        **{
                            k: v for k, v in model_data.items()
                            if k not in {
                                "id", "name", "streaming", "vision", "tool_calling",
                                "embeddings", "audio", "image_generation", "context_length",
                                "max_output_tokens", "input_per_million", "output_per_million", "extra",
                            }
                        },
                    },
                )
            )
        return models

    def capabilities(self) -> Dict[str, Any]:
        return dict(self.default_capabilities)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            models=self.available_models(),
            capabilities=ModelCapabilities(
                streaming=self.default_capabilities.get("streaming", True),
                vision=self.default_capabilities.get("vision", False),
                tool_calling=self.default_capabilities.get("tool_calling", True),
                embeddings=self.default_capabilities.get("embeddings", False),
                audio=self.default_capabilities.get("audio", False),
                image_generation=self.default_capabilities.get("image_generation", False),
                extra={k: v for k, v in self.default_capabilities.items()
                       if k not in {"streaming", "vision", "tool_calling", "embeddings", "audio", "image_generation"}},
            ),
            context_length=self.context_length_default,
            supports_streaming=self.default_capabilities.get("streaming", True),
            supports_vision=self.default_capabilities.get("vision", False),
            supports_tool_calling=self.default_capabilities.get("tool_calling", True),
            priority=self.priority_default,
            is_local=False,
        )

    def check_health(self) -> bool:
        """Check credentials and, for OpenAI-compatible providers, reachability."""
        if not self.api_key:
            return False
        if self.chat_api_style == "openai":
            try:
                request = Request(
                    self._models_url(),
                    headers=self._auth_headers(),
                    method="GET",
                )
                with urlopen(request, timeout=5):
                    return True
            except (HTTPError, URLError, TimeoutError, OSError):
                return False
            except Exception:
                return False
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.api_key is not None,
            "available": self.api_key is not None,
            "model_count": len(self.available_models()),
            "display_name": self.display_name,
        }

    def complete(self, request: RouteRequest) -> str:
        if self.chat_api_style == "openai":
            payload = self._chat_payload(request, stream=False)
            response = self._post_json(self._chat_url(), payload, request.timeout)
            return self._extract_text(response)
        raise NotImplementedError(
            f"{self.provider_name}.complete() has no transport adapter yet."
        )

    def complete_stream(self, request: RouteRequest) -> Iterator[str]:
        if self.chat_api_style == "openai":
            yield from self._stream_openai(request)
            return
        raise NotImplementedError(
            f"{self.provider_name}.complete_stream() has no transport adapter yet."
        )

    # ------------------------------------------------------------------
    # OpenAI-compatible transport
    # ------------------------------------------------------------------
    def _models_url(self) -> str:
        return self._base_url().rstrip("/") + "/models"

    def _chat_url(self) -> str:
        return self._base_url().rstrip("/") + "/chat/completions"

    def _base_url(self) -> str:
        if not self.api_base:
            raise RuntimeError(f"{self.provider_name} API base URL is not configured")
        return self.api_base

    def _auth_headers(self) -> Dict[str, str]:
        key = self.api_key
        if not key:
            raise RuntimeError(f"{self.display_name} API key is not configured")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _chat_payload(self, request: RouteRequest, *, stream: bool) -> Dict[str, Any]:
        model = request.model or (self.available_models()[0].id if self.available_models() else None)
        if not model:
            raise RuntimeError(f"No model is configured for provider '{self.name}'")
        messages: List[Dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.extra:
            for key in ("top_p", "stop", "presence_penalty", "frequency_penalty", "response_format", "tools", "tool_choice"):
                if key in request.extra:
                    payload[key] = request.extra[key]
        return payload

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: Optional[float]) -> Dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._auth_headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout or 60) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(self._http_error_message(exc.code, body)) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"{self.display_name} connection failed: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.display_name} returned invalid JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(self._error_object(data["error"]))
        return data

    def _stream_openai(self, request: RouteRequest) -> Iterator[str]:
        payload = self._chat_payload(request, stream=True)
        req = Request(
            self._chat_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={**self._auth_headers(), "Accept": "text/event-stream"},
            method="POST",
        )
        try:
            response = urlopen(req, timeout=request.timeout or 60)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(self._http_error_message(exc.code, body)) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"{self.display_name} connection failed: {exc}") from exc

        try:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if payload.get("error"):
                    raise RuntimeError(self._error_object(payload["error"]))
                for choice in payload.get("choices", []):
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield str(text)
        finally:
            response.close()

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content", "")
            if isinstance(content, list):
                return "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
            return str(content or "")
        if payload.get("output_text") is not None:
            return str(payload["output_text"])
        raise RuntimeError("Provider response contained no text output")

    @staticmethod
    def _error_object(error: Any) -> str:
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)
        return str(error)

    @classmethod
    def _http_error_message(cls, status: int, body: str) -> str:
        try:
            payload = json.loads(body)
            message = cls._error_object(payload.get("error", payload))
        except Exception:
            message = body.strip() or "request failed"
        return f"HTTP {status}: {message}"
