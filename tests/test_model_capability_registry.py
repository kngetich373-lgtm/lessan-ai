from core.model_router.base_provider import BaseModelProvider
from core.model_router.capabilities import ModelCapabilityRegistry
from core.model_router.models import ModelCapabilities, ModelInfo, ProviderInfo
from core.model_router.registry import ProviderRegistry


class StubProvider(BaseModelProvider):
    @property
    def name(self):
        return "stub"

    def __init__(self):
        self._info = ProviderInfo(
            name=self.name,
            models=[
                ModelInfo(id="stub-vision", capabilities=ModelCapabilities(vision=True, streaming=True)),
                ModelInfo(id="stub-text", capabilities=ModelCapabilities(streaming=True)),
            ],
        )

    def available_models(self):
        return list(self._info.models)

    def capabilities(self):
        return {"streaming": True, "vision": True, "local": True}

    def info(self):
        return self._info

    def complete(self, request):
        return "ok"

    def complete_stream(self, request):
        yield "ok"

    def check_health(self):
        return True

    def get_status(self):
        return {"healthy": True}


def test_registry_replaces_provider_model_metadata():
    registry = ModelCapabilityRegistry()
    registry.register_provider("demo", [ModelInfo(id="v1", capabilities=ModelCapabilities(vision=True))])
    assert registry.get("demo", "v1").capabilities.vision is True

    registry.register_provider("demo", [ModelInfo(id="v2", capabilities=ModelCapabilities(streaming=True))])
    assert registry.get("demo", "v1") is None
    assert registry.get("demo", "v2").capabilities.streaming is True


def test_provider_registry_syncs_capability_metadata():
    registry = ProviderRegistry()
    provider = StubProvider()
    registry.register(provider)

    assert registry.capabilities.get("stub", "stub-vision") is not None
    assert "stub" in registry.capabilities.providers_for_capability("vision")
    assert registry.with_capability("vision") == [provider]

    registry.unregister("stub")
    assert registry.capabilities.get("stub", "stub-vision") is None
