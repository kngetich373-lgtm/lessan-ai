"""Tests for the GatewayClient — sync API, async API, and circuit breaker."""

import asyncio
import json

import pytest

from core.gateway.client import (
    ChatCompletions,
    CircuitBreaker,
    GatewayClient,
)
from core.gateway.models import (
    GatewayResponse,
    GatewayStatus,
)


class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=0.1)
        assert cb.is_open("gw1") is False

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=10)
        cb.record_failure("gw1")
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is False
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is True

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=10)
        cb.record_failure("gw1")
        cb.record_failure("gw1")
        cb.record_success("gw1")
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is False

    def test_recovers_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown=0.05)
        cb.record_failure("gw1")
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is True
        import time
        time.sleep(0.1)
        assert cb.is_open("gw1") is False

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown=10)
        cb.record_failure("gw1")
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is True
        cb.reset("gw1")
        assert cb.is_open("gw1") is False

    def test_independent_per_gateway(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown=10)
        cb.record_failure("gw1")
        cb.record_failure("gw1")
        assert cb.is_open("gw1") is True
        assert cb.is_open("gw2") is False


class TestGatewayClientConstruction:
    def test_client_creation_without_api_keys(self):
        client = GatewayClient(auto_connect=False)
        assert client is not None
        assert client._initialized is False

    def test_client_has_backward_compat_methods(self):
        client = GatewayClient(auto_connect=False)
        assert hasattr(client, "chat")
        assert hasattr(client, "chat_json")
        assert hasattr(client, "vision")
        assert hasattr(client, "image_generate")
        assert hasattr(client, "available_models")

    def test_client_has_modern_api(self):
        client = GatewayClient(auto_connect=False)
        assert hasattr(client, "chat_completions")
        assert hasattr(client, "chat_stream")
        assert isinstance(client.chat_completions, ChatCompletions)

    def test_client_lazy_initialization(self):
        client = GatewayClient(auto_connect=False)
        assert client._initialized is False


class TestGatewayClientChatCompletions:
    def test_chat_completions_property(self):
        client = GatewayClient(auto_connect=False)
        assert isinstance(client.chat_completions, ChatCompletions)

    def test_messages_to_prompt_system(self):
        msgs = [
            {"role": "system", "content": "You are a chef"},
            {"role": "user", "content": "What is a tomato?"},
        ]
        prompt, system = ChatCompletions._messages_to_prompt(msgs, None)
        assert system == "You are a chef"
        assert "user: What is a tomato?" in prompt

    def test_messages_to_prompt_empty(self):
        prompt, system = ChatCompletions._messages_to_prompt([], None)
        assert prompt == ""

    def test_messages_with_multipart_content(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "Describe this"},
            ]},
        ]
        prompt, system = ChatCompletions._messages_to_prompt(msgs, None)
        assert "Describe this" in prompt


class TestGatewayClientSyncAPI:
    def test_chat_returns_string(self):
        """Client.chat should return a string (may be empty if no API)."""
        client = GatewayClient(auto_connect=False)
        result = client.chat("Hello", max_tokens=5)
        assert isinstance(result, str)

    def test_chat_json_handles_empty(self):
        """chat_json should raise on empty results gracefully."""
        client = GatewayClient(auto_connect=False)
        with pytest.raises((ValueError, Exception)):
            client.chat_json("return json", max_tokens=5)

    def test_available_models_returns_dict(self):
        client = GatewayClient(auto_connect=False)
        # Should not crash even with no gateways connected
        models = client.available_models()
        assert isinstance(models, dict)


class TestGatewayClientIntegration:
    def test_or_client_backward_compat(self):
        """from or_client import client must yield a GatewayClient."""
        from or_client import client
        assert isinstance(client, GatewayClient)
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

    def test_client_fallback_flag(self):
        client = GatewayClient(auto_connect=False)
        assert client._fallback is True

    def test_circuit_breaker_prevents_failing_gateway(self):
        from core.gateway.client import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, cooldown=10)
        cb.record_failure("test_gw")
        assert cb.is_open("test_gw") is True
