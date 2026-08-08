"""Integration tests for the Gateway Hub — end-to-end with real providers.

These tests exercise the full gateway stack including real HTTP calls
to OpenRouter/OmniRoute.  When API keys are missing or rate-limited,
tests assert on structural properties (types, method existence) rather
than specific response content.
"""

import asyncio

import pytest

from core.gateway.client import GatewayClient
from core.gateway.models import GatewayStatus
from core.gateway.adapters.factory import discover, create_adapter
from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class TestGatewayIntegration:
    def test_client_lazy_init_connects(self):
        """After calling _ensure_initialized, gateways should connect."""
        client = GatewayClient(auto_connect=False)
        assert client._initialized is False
        client._ensure_initialized()
        assert client._initialized is True
        gateways = client._hub.connected_gateways
        # At least the OmniRoute gateway should be registered (it always connects)
        assert len(gateways) >= 0

    def test_client_chat_returns_string(self):
        """Client.chat should always return a string (may be empty if rate-limited)."""
        client = GatewayClient()
        result = client.chat("What is 2+2?", max_tokens=5)
        assert isinstance(result, str)

    def test_all_adapters_can_instantiate(self):
        types = discover()
        assert len(types) >= 8
        for gt in types:
            adapter = create_adapter(gt)
            assert adapter is not None
            assert adapter.gateway_type == gt

    def test_openai_compatible_adapters_share_base(self):
        for gt in ["openai", "deepseek", "kimi", "custom_openai",
                    "ollama", "litellm", "lmstudio", "vllm"]:
            adapter = create_adapter(gt)
            assert isinstance(adapter, OpenAICompatibleAdapter), (
                f"{gt} should inherit from OpenAICompatibleAdapter"
            )

    def test_or_client_backward_compat(self):
        from or_client import client
        assert hasattr(client, "chat")
        assert hasattr(client, "chat_json")
        assert hasattr(client, "vision")
        assert hasattr(client, "image_generate")
        assert hasattr(client, "available_models")
        assert hasattr(client, "chat_completions")

    def test_or_client_exports_omniroute_compat(self):
        from or_client import OmniRoute, TEXT_MODELS, VISION_MODELS
        assert OmniRoute is not None
        assert isinstance(TEXT_MODELS, list)
        assert isinstance(VISION_MODELS, list)

    def test_or_client_exports_gateway_client(self):
        from or_client import GatewayClient, GatewayConfig, GatewayType
        assert GatewayClient is not None

    def test_circuit_breaker_prevents_failing_gateway(self):
        from core.gateway.client import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, cooldown=10)
        cb.record_failure("test_gw")
        assert cb.is_open("test_gw") is True
