"""Gateway Client — the main entry point for the Gateway Hub.

The ``GatewayClient`` wraps the :class:`GatewayHub` and provides:

* **Backward-compatible synchronous API** (``chat``, ``chat_json``,
  ``vision``, ``image_generate``, ``available_models``) matching the
  existing ``omniroute.client`` interface so that every existing caller
  in ``actions/*``, ``agent/*``, and ``lessan_ai_agents/*`` continues to
  work without code changes.

* **Modern asynchronous API** via the ``chat_completions`` namespace
  (``await client.chat_completions.create(...)``) per the build prompt.

* **Circuit-breaker / fallback** — if the preferred gateway fails, the
  client transparently retries on the next available gateway.  As a
  last resort it delegates to the legacy ``omniroute.client``.

The client auto-connects to whatever gateways are available given the
current environment (API keys in env vars or ``config/api_keys.json``).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Union

from core.gateway.adapters.factory import ADAPTER_REGISTRY, create_adapter
from core.gateway.adapters.omniroute_adapter import OmniRouteAdapter
from core.gateway.exceptions import GatewayError
from core.gateway.hub import GatewayHub
from core.gateway.models import (
    GatewayConfig,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    GatewayType,
)
from core.logging import get_logger

logger = get_logger("GatewayClient")

_DEFAULT_SYSTEM = (
    "You are a component of Lessan, an AI assistant. "
    "Be concise, helpful, and precise."
)
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_PRIORITY = 100


class _LoopRunner:
    """Runs coroutines on a dedicated background event loop.

    This allows synchronous callers (which may already be inside an
    asyncio event loop) to invoke async gateway methods without
    ``RuntimeError: This event loop is already running``.
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._start()

    def _start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run, name="gateway-client-loop", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro):
        """Submit a coroutine and block until it completes."""
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def create_task(self, coro):
        """Submit a coroutine and return its asyncio Future immediately."""
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=2)
            self._loop = None
            self._thread = None


# --------------------------------------------------------------------------- #
# ChatCompletions namespace (async API per build prompt)
# --------------------------------------------------------------------------- #


class ChatCompletions:
    """Async chat-completions namespace (OpenAI-style ``create``).

    Usage::

        response = await client.chat_completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            stream=False,
        )
    """

    def __init__(self, client: "GatewayClient") -> None:
        self._client = client

    async def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        provider: Optional[str] = None,
        gateway: Optional[str] = None,
        **kwargs: Any,
    ) -> Union[GatewayResponse, "AsyncIteratorWrapper"]:
        """Execute a chat completion, optionally streaming.

        Returns a single :class:`GatewayResponse` when ``stream=False``,
        or an async iterator yielding chunks when ``stream=True``.
        """
        prompt, system = self._messages_to_prompt(messages or [], system)
        request = GatewayRequest(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            temperature=temperature if temperature is not None else _DEFAULT_TEMPERATURE,
            stream=stream,
            provider=provider,
            gateway=gateway,
        )
        if stream:
            return AsyncIteratorWrapper(self._client._stream(request))
        return await self._client._chat_async(request)

    @staticmethod
    def _messages_to_prompt(
        messages: List[Dict[str, Any]], system: Optional[str]
    ) -> tuple:
        """Convert OpenAI-style messages into the Gateway Hub prompt/system pair."""
        extracted_system = system
        prompt_parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "") for c in content if c.get("type") == "text"
                ]
                content = " ".join(text_parts)
            if role == "system":
                if extracted_system:
                    extracted_system += "\n" + str(content)
                else:
                    extracted_system = str(content)
            elif role in ("user", "assistant", "tool"):
                prompt_parts.append(f"{role}: {content}")
        if not prompt_parts:
            return "", extracted_system
        return "\n".join(prompt_parts), extracted_system


class AsyncIteratorWrapper:
    """Wraps an async iterator so callers can ``async for`` over it."""

    def __init__(self, iterator):
        self._iterator = iterator

    def __aiter__(self):
        return self._iterator

    def __anext__(self):
        return self._iterator.__anext__()


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #


class CircuitBreaker:
    """Simple per-gateway circuit breaker.

    After ``failure_threshold`` consecutive failures, the gateway is
    marked OPEN and skipped for ``cooldown`` seconds.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._failures: Dict[str, int] = {}
        self._opened_at: Dict[str, float] = {}

    def record_success(self, gateway_id: str) -> None:
        self._failures.pop(gateway_id, None)
        self._opened_at.pop(gateway_id, None)

    def record_failure(self, gateway_id: str) -> None:
        count = self._failures.get(gateway_id, 0) + 1
        self._failures[gateway_id] = count
        if count >= self._failure_threshold:
            self._opened_at[gateway_id] = time.monotonic()
            logger.warning(
                f"Circuit breaker OPEN for gateway '{gateway_id}' "
                f"after {count} failures."
            )

    def is_open(self, gateway_id: str) -> bool:
        if gateway_id not in self._opened_at:
            return False
        opened_at = self._opened_at[gateway_id]
        if time.monotonic() - opened_at >= self._cooldown:
            self._opened_at.pop(gateway_id, None)
            self._failures.pop(gateway_id, None)
            logger.info(f"Circuit breaker HALF-OPEN for '{gateway_id}'.")
            return False
        return True

    def reset(self, gateway_id: str) -> None:
        self._failures.pop(gateway_id, None)
        self._opened_at.pop(gateway_id, None)


# --------------------------------------------------------------------------- #
# GatewayClient
# --------------------------------------------------------------------------- #


class GatewayClient:
    """Main entry point for LLM gateway access.

    Wraps :class:`GatewayHub` and provides both the legacy synchronous
    API (``chat``, ``chat_json``, ``vision``, etc.) and the modern async
    API (``chat_completions.create``, ``chat_stream``).
    """

    def __init__(
        self,
        hub: Optional[GatewayHub] = None,
        *,
        auto_connect: bool = True,
        fallback_to_omniroute: bool = True,
    ) -> None:
        self._hub = hub or GatewayHub()
        self._loop_runner = _LoopRunner()
        self._breaker = CircuitBreaker()
        self._fallback = fallback_to_omniroute
        self._omniroute_client: Any = None
        self._initialized = False
        self._init_lock = threading.Lock()

        # Register all known adapters with the hub
        for gateway_type, adapter_cls in ADAPTER_REGISTRY.items():
            adapter = adapter_cls()
            self._hub.register_adapter(adapter)

        # Connection is deferred to _ensure_initialized() on first use

    def _ensure_initialized(self) -> None:
        """Lazily connect gateways on first use (avoids import-time network)."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._auto_connect()
            self._initialized = True

    # ------------------------------------------------------------------ #
    # Configuration / auto-connect
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_api_keys() -> Dict[str, str]:
        """Load API keys from config/api_keys.json (same as omniroute.py)."""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "api_keys.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _auto_connect(self) -> None:
        """Connect to whatever gateways have credentials available."""
        keys = self._load_api_keys()

        configs: List[GatewayConfig] = []

        # OmniRoute — always available (wraps omniroute.py which handles
        # its own key resolution)
        configs.append(GatewayConfig(
            gateway_id="omniroute",
            gateway_type=GatewayType.OMNIRoute,
            name="OmniRoute",
            display_name="OmniRoute (fallback)",
            priority=1000,  # lowest priority (fallback)
        ))

        # OpenRouter
        or_key = keys.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY", "")
        if or_key:
            configs.append(GatewayConfig(
                gateway_id="openrouter",
                gateway_type=GatewayType.OPENROUTER,
                name="OpenRouter",
                priority=10,
                api_key=or_key,
            ))

        # OpenAI
        oa_key = keys.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        if oa_key:
            configs.append(GatewayConfig(
                gateway_id="openai",
                gateway_type=GatewayType.OPENAI,
                name="OpenAI",
                priority=20,
                api_key=oa_key,
            ))

        # Gemini
        gem_key = keys.get("gemini_api_key") or os.environ.get("GOOGLE_API_KEY", "")
        if gem_key:
            configs.append(GatewayConfig(
                gateway_id="gemini",
                gateway_type=GatewayType.GEMINI,
                name="Gemini",
                priority=30,
                api_key=gem_key,
            ))

        # Anthropic
        an_key = keys.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if an_key:
            configs.append(GatewayConfig(
                gateway_id="anthropic",
                gateway_type=GatewayType.ANTHROPIC,
                name="Anthropic",
                priority=40,
                api_key=an_key,
            ))

        # DeepSeek
        ds_key = keys.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
        if ds_key:
            configs.append(GatewayConfig(
                gateway_id="deepseek",
                gateway_type=GatewayType.DEESEEK,
                name="DeepSeek",
                priority=50,
                api_key=ds_key,
            ))

        # Sort by priority (lower = higher priority) and connect
        configs.sort(key=lambda c: c.priority)
        for cfg in configs:
            try:
                self._hub.connect(cfg)
            except GatewayError as exc:
                logger.warning(f"Gateway '{cfg.gateway_id}' connect failed: {exc}")

        self._initialized = True
        logger.info(
            f"GatewayClient ready with {len(self._hub.connected_gateways)} connected gateway(s)."
        )

    # ------------------------------------------------------------------ #
    # Internal: routing with circuit-breaker + fallback
    # ------------------------------------------------------------------ #

    def _select_gateway(self, request: GatewayRequest) -> str:
        """Pick the highest-priority healthy gateway.

        If the request specifies a gateway or provider, use that directly.
        Otherwise, iterate connected gateways by priority and skip any
        that the circuit breaker has opened.
        """
        if request.gateway:
            return request.gateway
        if request.provider:
            from core.gateway.registry import GatewayRegistry  # noqa
            provider = self._hub.get_provider(request.provider)
            if provider is not None:
                return provider.gateway_id

        candidates = sorted(self._hub.connected_gateways, key=lambda r: r.config.priority)
        for record in candidates:
            if not self._breaker.is_open(record.config.gateway_id):
                return record.config.gateway_id
        # All breakers open — fall back to any connected gateway
        if candidates:
            return candidates[0].config.gateway_id
        raise GatewayError("No gateways are connected.")

    async def _chat_async(self, request: GatewayRequest) -> GatewayResponse:
        """Route a chat request through the hub with circuit-breaker + fallback."""
        self._ensure_initialized()
        # Try each connected gateway in priority order
        candidates = sorted(self._hub.connected_gateways, key=lambda r: r.config.priority)
        last_error = ""
        for record in candidates:
            gw_id = record.config.gateway_id
            if self._breaker.is_open(gw_id):
                continue
            try:
                gw_request = GatewayRequest(
                    prompt=request.prompt,
                    system=request.system,
                    model=request.model,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=request.stream,
                    gateway=gw_id,
                )
                resp = await record.adapter.chat(record, gw_request)
                if resp.success:
                    self._breaker.record_success(gw_id)
                    return resp
                last_error = resp.error or "unknown error"
                self._breaker.record_failure(gw_id)
            except Exception as exc:  # noqa: BLE001
                self._breaker.record_failure(gw_id)
                last_error = str(exc)
                logger.warning(f"Gateway '{gw_id}' chat failed: {exc}")

        # All gateways failed — try legacy omniroute fallback
        if self._fallback:
            text = self._legacy_omniroute_chat(request)
            if text:
                return GatewayResponse(
                    text=text, provider="omniroute", gateway="omniroute",
                    success=True,
                )

        return GatewayResponse(
            text="", provider="", gateway="",
            error=last_error or "All gateways failed.",
            success=False,
        )

    def _legacy_omniroute_chat(self, request: GatewayRequest) -> str:
        """Direct fallback to omniroute.client (the pre-gateway path)."""
        try:
            if self._omniroute_client is None:
                from omniroute import client as omniclient
                self._omniroute_client = omniclient
            return self._omniroute_client.chat(
                request.prompt,
                system=request.system or _DEFAULT_SYSTEM,
                model=request.model,
                max_tokens=request.max_tokens or _DEFAULT_MAX_TOKENS,
                temperature=request.temperature or _DEFAULT_TEMPERATURE,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Legacy omniroute fallback failed: {exc}")
            return ""

    async def _stream(self, request: GatewayRequest):
        """Stream a chat response, trying gateways in priority order."""
        self._ensure_initialized()
        candidates = sorted(self._hub.connected_gateways, key=lambda r: r.config.priority)
        for record in candidates:
            gw_id = record.config.gateway_id
            if self._breaker.is_open(gw_id):
                continue
            try:
                gw_request = GatewayRequest(
                    prompt=request.prompt,
                    system=request.system,
                    model=request.model,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=True,
                    gateway=gw_id,
                )
                async for chunk in record.adapter.stream_chat(record, gw_request):
                    if chunk.success or chunk.text:
                        yield chunk
                    else:
                        continue
                self._breaker.record_success(gw_id)
                return
            except Exception as exc:  # noqa: BLE001
                self._breaker.record_failure(gw_id)
                logger.warning(f"Gateway '{gw_id}' stream failed: {exc}")

        # Fallback: non-streaming via legacy omniroute
        text = self._legacy_omniroute_chat(request)
        if text:
            yield GatewayResponse(
                text=text, provider="omniroute", gateway="omniroute",
                success=True,
            )

    # ------------------------------------------------------------------ #
    # Synchronous backward-compatible API (matches omniroute.client)
    # ------------------------------------------------------------------ #

    def chat(
        self,
        prompt: str,
        system: str = _DEFAULT_SYSTEM,
        model: Optional[str] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> str:
        """Backward-compatible synchronous chat. Returns text."""
        self._ensure_initialized()
        request = GatewayRequest(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        try:
            resp = self._loop_runner.run(self._chat_async(request))
            if resp.success:
                return resp.text
            # Fall back to legacy omniroute
            text = self._legacy_omniroute_chat(request)
            if text:
                return text
            logger.error(f"GatewayClient.chat failed: {resp.error}")
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.error(f"GatewayClient.chat error: {exc}")
            text = self._legacy_omniroute_chat(request)
            if text:
                return text
            return ""

    def chat_json(
        self,
        prompt: str,
        system: str = "Return ONLY valid JSON. No markdown fences, no extra text.",
        model: Optional[str] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> dict:
        """Backward-compatible synchronous JSON chat. Returns parsed dict."""
        text = self.chat(prompt, system=system, model=model, max_tokens=max_tokens, temperature=0.2)
        clean = text.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}\nRaw: {text[:200]}")
            raise ValueError(f"Model returned unparseable JSON: {e}") from e

    def vision(
        self,
        prompt: str,
        image_b64: str,
        mime: str = "image/png",
        system: str = "Analyze the image and describe what you see clearly and concisely.",
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Backward-compatible synchronous vision. Routes through OmniRoute."""
        try:
            if self._omniroute_client is None:
                from omniroute import client as omniclient
                self._omniroute_client = omniclient
            return self._omniroute_client.vision(
                prompt, image_b64, mime, system, model, max_tokens
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"GatewayClient.vision error: {exc}")
            return ""

    def image_generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        n: int = 1,
        **kwargs: Any,
    ) -> str:
        """Backward-compatible synchronous image generation."""
        try:
            if self._omniroute_client is None:
                from omniroute import client as omniclient
                self._omniroute_client = omniclient
            return self._omniroute_client.image_generate(prompt, width=width, height=height, n=n)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"GatewayClient.image_generate error: {exc}")
            return ""

    def available_models(self) -> dict:
        """Return available models from the hub and legacy omniroute."""
        self._ensure_initialized()
        models = {}
        for record in self._hub.connected_gateways:
            try:
                providers = self._loop_runner.run(record.adapter.discover(record))
                for p in providers:
                    models[p.provider_id] = [m.model_id for m in p.models]
            except Exception:  # noqa: BLE001
                pass
        # Merge legacy omniroute models
        try:
            if self._omniroute_client is None:
                from omniroute import client as omniclient
                self._omniroute_client = omniclient
            legacy = self._omniroute_client.available_models()
            models.update(legacy)
        except Exception:  # noqa: BLE001
            pass
        return models

    # ------------------------------------------------------------------ #
    # Async API (modern)
    # ------------------------------------------------------------------ #

    async def chat_stream(
        self,
        prompt: str,
        system: str = _DEFAULT_SYSTEM,
        model: Optional[str] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ):
        """Async streaming chat. Yields ``GatewayResponse`` chunks."""
        self._ensure_initialized()
        request = GatewayRequest(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in self._stream(request):
            yield chunk

    def get_hub(self) -> GatewayHub:
        """Expose the underlying GatewayHub for advanced use."""
        return self._hub

    def shutdown(self) -> None:
        """Clean up background resources."""
        self._loop_runner.stop()
        for gw_id in [r.config.gateway_id for r in self._hub.connected_gateways]:
            try:
                self._hub.disconnect(gw_id)
            except Exception:  # noqa: BLE001
                pass

    # Properties for compatibility
    @property
    def chat_completions(self) -> ChatCompletions:
        return ChatCompletions(self)

    @property
    def text_models(self) -> list:
        from omniroute import TEXT_MODELS
        return TEXT_MODELS

    @property
    def vision_models(self) -> list:
        from omniroute import VISION_MODELS
        return VISION_MODELS

    def __del__(self):
        try:
            self._loop_runner.stop()
        except Exception:  # noqa: BLE001
            pass
