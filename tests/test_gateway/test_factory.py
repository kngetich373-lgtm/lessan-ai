"""Tests for the adapter factory and adapter registration."""

import pytest

from core.gateway.adapters.base_adapter import BaseGatewayAdapter
from core.gateway.adapters.factory import (
    ADAPTER_REGISTRY,
    all_adapters,
    create_adapter,
    discover,
    get_adapter_class,
    register_adapter,
)
from core.gateway.adapters.openai_adapter import OpenAIAdapter
from core.gateway.adapters.openrouter_adapter import OpenRouterAdapter
from core.gateway.adapters.omniroute_adapter import OmniRouteAdapter
from core.gateway.adapters.gemini_adapter import GeminiAdapter
from core.gateway.adapters.anthropic_adapter import AnthropicAdapter
from core.gateway.adapters.deepseek_adapter import DeepSeekAdapter
from core.gateway.adapters.kimi_adapter import KimiAdapter
from core.gateway.adapters.custom_openai_adapter import CustomOpenAIAdapter
from core.gateway.adapters.ollama_adapter import OllamaAdapter
from core.gateway.adapters.litellm_adapter import LiteLLMAdapter
from core.gateway.adapters.lmstudio_adapter import LMStudioAdapter
from core.gateway.adapters.vllm_adapter import VLLMAdapter


EXPECTED_TYPES = [
    "omniroute", "openrouter", "openai", "deepseek", "kimi",
    "custom_openai", "ollama", "litellm", "lmstudio", "vllm",
    "gemini", "anthropic",
]


class TestAdapterFactory:
    def test_discover_returns_all_types(self):
        types = discover()
        assert set(types) == set(EXPECTED_TYPES)

    def test_all_adapters_instantiate(self):
        adapters = all_adapters()
        assert len(adapters) == len(EXPECTED_TYPES)

    def test_create_adapter_known_type(self):
        adapter = create_adapter("openai")
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.gateway_type == "openai"

    def test_create_adapter_unknown_type(self):
        adapter = create_adapter("nonexistent")
        assert adapter is None

    def test_get_adapter_class(self):
        cls = get_adapter_class("openrouter")
        assert cls is OpenRouterAdapter

    def test_get_adapter_class_unknown(self):
        assert get_adapter_class("unknown") is None


class TestAllAdaptersInheritBase:
    @pytest.mark.parametrize("gateway_type", EXPECTED_TYPES)
    def test_adapter_inherits_base(self, gateway_type):
        adapter = create_adapter(gateway_type)
        assert isinstance(adapter, BaseGatewayAdapter)
        assert adapter.gateway_type == gateway_type

    @pytest.mark.parametrize("gateway_type", EXPECTED_TYPES)
    def test_adapter_has_required_methods(self, gateway_type):
        adapter = create_adapter(gateway_type)
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "authenticate")
        assert hasattr(adapter, "health")
        assert hasattr(adapter, "discover")
        assert hasattr(adapter, "list_providers")
        assert hasattr(adapter, "provider_details")
        assert hasattr(adapter, "chat")
        assert hasattr(adapter, "stream_chat")
        assert hasattr(adapter, "embeddings")
        assert hasattr(adapter, "image_generation")
        assert hasattr(adapter, "speech")
        assert hasattr(adapter, "supports_streaming")
        assert hasattr(adapter, "supports_tools")
        assert hasattr(adapter, "supports_reasoning")


class TestOpenAICompatibleAdapters:
    @pytest.mark.parametrize("gateway_type,expected_cls", [
        ("openai", OpenAIAdapter),
        ("deepseek", DeepSeekAdapter),
        ("kimi", KimiAdapter),
        ("custom_openai", CustomOpenAIAdapter),
        ("ollama", OllamaAdapter),
        ("litellm", LiteLLMAdapter),
        ("lmstudio", LMStudioAdapter),
        ("vllm", VLLMAdapter),
    ])
    def test_openai_compatible_inherits_from_base(self, gateway_type, expected_cls):
        from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter
        adapter = create_adapter(gateway_type)
        assert isinstance(adapter, OpenAICompatibleAdapter)
        assert isinstance(adapter, expected_cls)

    def test_register_custom_adapter(self):
        class CustomAdapter(BaseGatewayAdapter):
            gateway_type = "custom_test"
            async def connect(self, config):
                from core.gateway.models import GatewayRecord, GatewayStatus
                return GatewayRecord(config=config, status=GatewayStatus.CONNECTING)
            async def disconnect(self, record): pass
            async def authenticate(self, record): return True
            async def health(self, record): return record
            async def discover(self, record): return []
            async def list_providers(self, record): return []
            async def provider_details(self, record, pid): return None
            async def chat(self, record, request): pass
            async def stream_chat(self, record, request):
                yield
            async def embeddings(self, record, texts, model=None): return []
            async def image_generation(self, record, prompt, model=None, **kw): return b""
            async def speech(self, record, text, model=None, **kw): return b""
            def supports_streaming(self, record): return True
            def supports_tools(self, record): return True
            def supports_reasoning(self, record): return False
            def supports_audio(self, record): return False
            def supports_images(self, record): return False
            def supports_video(self, record): return False
            def supports_embeddings(self, record): return False

        register_adapter("custom_test", CustomAdapter)
        assert "custom_test" in ADAPTER_REGISTRY
        adapter = create_adapter("custom_test")
        assert adapter is not None
        assert adapter.gateway_type == "custom_test"
        # Clean up
        del ADAPTER_REGISTRY["custom_test"]
