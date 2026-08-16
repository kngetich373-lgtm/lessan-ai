"""Gateway integration tests.

Tests marked ``live`` perform real gateway/network work and are excluded from
normal CI. Structural tests remain safe to run without API credentials.
"""

import pytest

from core.gateway.client import GatewayClient
from core.gateway.adapters.factory import discover, create_adapter
from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


class TestGatewayIntegration:
    @pytest.mark.live
    def test_client_lazy_init_connects(self):
        client = GatewayClient(auto_connect=False)
        assert client._initialized is False
        client._ensure_initialized()
        assert client._initialized is True
        assert len(client._hub.connected_gateways) >= 0

    @pytest.mark.live
    def test_client_chat_returns_string(self):
        client = GatewayClient()
        result = client.chat("What is 2+2?", max_tokens=5)
        assert isinstance(result, str)

    def test_all_adapters_can_instantiate(self):
        types = discover()
        assert len(types) >= 8
        for gateway_type in types:
            adapter = create_adapter(gateway_type)
            assert adapter is not None
            assert adapter.gateway_type == gateway_type

    def test_openai_compatible_adapters_share_base(self):
        for gateway_type in [
            "openai", "deepseek", "kimi", "custom_openai",
            "ollama", "litellm", "lmstudio", "vllm",
        ]:
            adapter = create_adapter(gateway_type)
            assert isinstance(adapter, OpenAICompatibleAdapter), (
                f"{gateway_type} should inherit from OpenAICompatibleAdapter"
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
        assert GatewayConfig is not None
        assert GatewayType is not None

    def test_circuit_breaker_prevents_failing_gateway(self):
        from core.gateway.client import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, cooldown=10)
        cb.record_failure("test_gw")
        assert cb.is_open("test_gw") is True
