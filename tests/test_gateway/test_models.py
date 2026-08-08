"""Tests for gateway data models."""

import pytest

from core.gateway.models import (
    GatewayCapabilities,
    GatewayConfig,
    GatewayMetrics,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    GatewayType,
    ModelRecord,
    ProviderRecord,
    CostMetadata,
)


class TestGatewayConfig:
    def test_defaults(self):
        cfg = GatewayConfig(gateway_id="test", gateway_type=GatewayType.OPENAI)
        assert cfg.gateway_id == "test"
        assert cfg.gateway_type == GatewayType.OPENAI
        assert cfg.enabled is True
        assert cfg.priority == 100
        assert cfg.api_key == ""
        assert cfg.timeout == 30.0

    def test_name_inference(self):
        cfg = GatewayConfig(gateway_id="mygw", gateway_type=GatewayType.OPENAI)
        assert cfg.name == "mygw"
        assert cfg.display_name == "openai"

    def test_explicit_names(self):
        cfg = GatewayConfig(
            gateway_id="mygw",
            gateway_type=GatewayType.OPENAI,
            name="My Gateway",
            display_name="Custom Display",
        )
        assert cfg.name == "My Gateway"
        assert cfg.display_name == "Custom Display"


class TestGatewayStatus:
    def test_is_connected(self):
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        rec = GatewayRecord(config=cfg, status=GatewayStatus.CONNECTED)
        assert rec.is_connected is True

    def test_is_not_connected_when_disconnected(self):
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        rec = GatewayRecord(config=cfg, status=GatewayStatus.DISCONNECTED)
        assert rec.is_connected is False

    def test_is_healthy(self):
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        rec = GatewayRecord(config=cfg, status=GatewayStatus.CONNECTED)
        assert rec.is_healthy is True
        rec.consecutive_failures = 1
        assert rec.is_healthy is False


class TestGatewayCapabilities:
    def test_supports(self):
        caps = GatewayCapabilities(streaming=True, tools=False, extra={"custom": True})
        assert caps.supports("streaming") is True
        assert caps.supports("tools") is False
        assert caps.supports("custom") is True
        assert caps.supports("nonexistent") is False

    def test_supports_case_insensitive(self):
        caps = GatewayCapabilities(streaming=True)
        assert caps.supports("STREAMING") is True
        assert caps.supports("StreamIng") is True


class TestGatewayRequest:
    def test_defaults(self):
        req = GatewayRequest(prompt="hello")
        assert req.prompt == "hello"
        assert req.max_tokens == 512
        assert req.temperature == 0.7
        assert req.stream is False
        assert req.model is None

    def test_with_all_fields(self):
        req = GatewayRequest(
            prompt="test",
            system="you are helpful",
            model="gpt-4o",
            max_tokens=100,
            temperature=0.5,
            stream=True,
            provider="openai",
            gateway="main",
            required_capabilities=["streaming"],
        )
        assert req.system == "you are helpful"
        assert req.model == "gpt-4o"
        assert req.stream is True


class TestGatewayResponse:
    def test_as_dict(self):
        resp = GatewayResponse(
            text="hello", model="gpt-4o", provider="openai",
            gateway="main", success=True, latency_ms=42.5,
        )
        d = resp.as_dict()
        assert d["text"] == "hello"
        assert d["success"] is True
        assert d["latency_ms"] == 42.5

    def test_error_response(self):
        resp = GatewayResponse(error="something went wrong", success=False)
        assert resp.success is False
        assert resp.error == "something went wrong"


class TestGatewayMetrics:
    def test_record_and_success_rate(self):
        m = GatewayMetrics(gateway_id="g1")
        m.record_request(True, 100.0, 50)
        m.record_request(True, 200.0, 100)
        m.record_request(False, 50.0, 0)
        assert m.total_requests == 3
        assert m.successful_requests == 2
        assert m.failed_requests == 1
        assert m.success_rate() == pytest.approx(2 / 3)

    def test_zero_requests(self):
        m = GatewayMetrics(gateway_id="g1")
        assert m.success_rate() == 0.0


class TestProviderAndModelRecords:
    def test_provider_as_dict(self):
        model = ModelRecord(
            model_id="gpt-4o",
            provider_id="openai",
            gateway_id="gw1",
            name="GPT-4o",
            context_length=128000,
        )
        provider = ProviderRecord(
            provider_id="openai",
            gateway_id="gw1",
            name="OpenAI",
            models=[model],
        )
        d = provider.as_dict()
        assert d["provider_id"] == "openai"
        assert d["name"] == "OpenAI"
        assert len(d["models"]) == 1
        assert d["models"][0]["model_id"] == "gpt-4o"

    def test_cost_metadata_as_dict(self):
        cost = CostMetadata(
            currency="USD",
            input_per_million=0.5,
            output_per_million=1.5,
            is_free=False,
        )
        d = cost.as_dict()
        assert d["currency"] == "USD"
        assert d["input_per_million"] == 0.5
        assert d["is_free"] is False
