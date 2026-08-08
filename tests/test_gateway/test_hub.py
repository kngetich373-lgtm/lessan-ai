"""Tests for GatewayHub and GatewayManager lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.gateway.hub import GatewayHub
from core.gateway.manager import GatewayManager
from core.gateway.models import (
    GatewayConfig,
    GatewayCapabilities,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    GatewayType,
    ModelRecord,
    ProviderRecord,
)
from core.gateway.registry import GatewayRegistry
from core.gateway.exceptions import (
    GatewayNotFoundError,
    GatewayConnectionError,
    AdapterNotFoundError,
)
from core.gateway.adapters.base_adapter import BaseGatewayAdapter


class TestGatewayHubLifecycle:
    def test_hub_creates_empty_registry(self):
        hub = GatewayHub()
        assert hub.connected_gateways == []
        assert hub.providers == []

    def test_cannot_connect_already_connected(self):
        hub = GatewayHub()
        adapter = AsyncMock(spec=BaseGatewayAdapter)
        adapter.gateway_type = "openai"
        adapter.connect = AsyncMock(return_value=GatewayRecord(
            config=GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI),
            status=GatewayStatus.CONNECTED,
        ))
        hub.register_adapter(adapter)
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        hub.connect(cfg)
        with pytest.raises(GatewayConnectionError):
            hub.connect(cfg)

    def test_connect_unknown_gateway_type(self):
        """Connecting with a GatewayType that has no registered adapter."""
        hub = GatewayHub()
        cfg = GatewayConfig(gateway_id="bad", gateway_type=GatewayType.GEMINI)
        with pytest.raises(AdapterNotFoundError):
            hub.connect(cfg)

    def test_disconnect_unregistered(self):
        hub = GatewayHub()
        with pytest.raises(GatewayNotFoundError):
            hub.disconnect("nonexistent")

    def test_enable_disable_unknown(self):
        hub = GatewayHub()
        with pytest.raises(GatewayNotFoundError):
            hub.enable("nonexistent")
        with pytest.raises(GatewayNotFoundError):
            hub.disable("nonexistent")

    def test_health_unknown_gateway(self):
        hub = GatewayHub()
        result = hub.health("nonexistent")
        assert result is None

    def test_discover_unknown_gateway(self):
        hub = GatewayHub()
        result = hub.discover("nonexistent")
        assert result == []


class TestGatewayHubChat:
    def _make_mock_hub(self):
        """Create a hub with a mock adapter that returns canned responses."""
        hub = GatewayHub()
        adapter = AsyncMock(spec=BaseGatewayAdapter)
        adapter.gateway_type = "openai"
        adapter.connect = AsyncMock(return_value=GatewayRecord(
            config=GatewayConfig(gateway_id="mock", gateway_type=GatewayType.OPENAI),
            status=GatewayStatus.CONNECTED,
        ))
        adapter.chat = AsyncMock(return_value=GatewayResponse(
            text="OK", model="mock", provider="mock",
            gateway="mock", success=True,
        ))
        adapter.discover = AsyncMock(return_value=[
            ProviderRecord(
                provider_id="openai", gateway_id="mock", name="Mock",
                models=[ModelRecord(
                    model_id="m1", provider_id="openai", gateway_id="mock",
                    name="M1", context_length=4096,
                    capabilities=GatewayCapabilities(streaming=True),
                )],
            )
        ])
        hub.register_adapter(adapter)
        hub.connect(GatewayConfig(
            gateway_id="mock", gateway_type=GatewayType.OPENAI,
            priority=10,
        ))
        return hub

    def test_chat_returns_response(self):
        hub = self._make_mock_hub()
        from core.gateway.models import GatewayResponse
        req = GatewayRequest(
            prompt="Hello", system="Reply with OK", max_tokens=5, temperature=0.1,
        )
        resp = hub.chat(req)
        assert isinstance(resp, GatewayResponse)
        assert resp.success is True
        assert resp.text == "OK"

    def test_chat_unavailable_gateway(self):
        hub = GatewayHub()
        req = GatewayRequest(prompt="hello", gateway="nonexistent")
        resp = hub.chat(req)
        assert resp.success is False
        assert "not available" in resp.error

    def test_chat_resolves_default_gateway(self):
        hub = self._make_mock_hub()
        req = GatewayRequest(prompt="Hello", max_tokens=5)
        resp = hub.chat(req)
        assert resp.success is True

    def test_chat_streaming(self):
        hub = self._make_mock_hub()
        record = hub._registry.get_gateway("mock")
        adapter = record.adapter
        async def _mock_stream(rec, request):
            yield GatewayResponse(text="chunk1", model="mock", provider="mock", gateway="mock", success=True)
            yield GatewayResponse(text="chunk2", model="mock", provider="mock", gateway="mock", success=True)
        adapter.stream_chat = _mock_stream
        req = GatewayRequest(prompt="Hello", max_tokens=5, stream=True)
        gen = hub.stream_chat(req)
        chunks = asyncio.new_event_loop().run_until_complete(
            self._collect_async(gen)
        )
        assert len(chunks) == 2
        assert chunks[0].text == "chunk1"

    @staticmethod
    async def _collect_async(gen):
        results = []
        async for chunk in gen:
            results.append(chunk)
        return results


class TestGatewayRegistry:
    def test_register_and_lookup_gateway(self):
        reg = GatewayRegistry()
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        rec = GatewayRecord(config=cfg)
        reg.register_gateway(rec)
        assert reg.get_gateway("g1") is rec
        assert reg.get_gateway("g2") is None

    def test_unregister_removes_providers(self):
        reg = GatewayRegistry()
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        reg.register_gateway(GatewayRecord(config=cfg))
        reg.register_provider(ProviderRecord(
            provider_id="p1", gateway_id="g1", name="P1",
        ))
        assert reg.get_provider("p1") is not None
        reg.unregister_gateway("g1")
        assert reg.get_provider("p1") is None

    def test_healthy_gateways(self):
        reg = GatewayRegistry()
        cfg_ok = GatewayConfig(gateway_id="ok", gateway_type=GatewayType.OPENAI)
        cfg_bad = GatewayConfig(gateway_id="bad", gateway_type=GatewayType.OPENAI)
        rec_ok = GatewayRecord(config=cfg_ok, status=GatewayStatus.CONNECTED)
        rec_bad = GatewayRecord(config=cfg_bad, status=GatewayStatus.ERROR)
        reg.register_gateway(rec_ok)
        reg.register_gateway(rec_bad)
        assert len(reg.healthy_gateways()) == 1

    def test_clear(self):
        reg = GatewayRegistry()
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        reg.register_gateway(GatewayRecord(config=cfg))
        reg.register_provider(ProviderRecord(provider_id="p1", gateway_id="g1", name="P1"))
        reg.clear()
        assert reg.get_gateway("g1") is None
        assert reg.get_provider("p1") is None
