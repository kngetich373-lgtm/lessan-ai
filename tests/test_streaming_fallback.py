from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import ModelCapabilities, ModelInfo, ProviderInfo, RouteRequest
from core.model_router.registry import ProviderRegistry
from core.model_router.router import ModelRouter


class FailingStreamProvider(BaseModelProvider):
    name = "failing"

    def info(self):
        return ProviderInfo(name=self.name, models=[ModelInfo(id="fail", capabilities=ModelCapabilities(streaming=True))], supports_streaming=True)

    def available_models(self):
        return self.info().models

    def capabilities(self):
        return {"streaming": True}

    def complete(self, request):
        return "unused"

    def complete_stream(self, request):
        yield "partial"
        raise RuntimeError("stream disconnected")

    def check_health(self):
        return True

    def get_status(self):
        return {"healthy": True}


class WorkingProvider(BaseModelProvider):
    name = "working"

    def info(self):
        return ProviderInfo(name=self.name, models=[ModelInfo(id="ok", capabilities=ModelCapabilities(streaming=True))], supports_streaming=True)

    def available_models(self):
        return self.info().models

    def capabilities(self):
        return {"streaming": True}

    def complete(self, request):
        return "ok"

    def complete_stream(self, request):
        yield "fallback"

    def check_health(self):
        return True

    def get_status(self):
        return {"healthy": True}


def test_stream_failure_is_recovered_by_next_provider():
    registry = ProviderRegistry()
    registry.register(FailingStreamProvider())
    registry.register(WorkingProvider())

    router = ModelRouter(registry=registry)
    result = router.route(RouteRequest(prompt="hello", stream=True))
    chunks = list(result.stream or ())

    assert result.success is True
    assert result.provider == "working"
    assert chunks == ["fallback"]
    assert result.fallback_chain == ["failing", "working"]
