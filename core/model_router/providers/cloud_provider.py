"""Cloud Provider Base — common patterns for cloud-based AI providers."""

from typing import Any, Dict, List, Optional

from core.logging import get_logger
from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import CostMetadata, ModelCapabilities, ModelInfo, ProviderInfo, RouteRequest

logger = get_logger("CloudProvider")


class CloudProviderBase(BaseModelProvider):
    """Base class for cloud-based providers with common configuration handling."""

    provider_name: str = "cloud"
    display_name: str = "Cloud Provider"
    api_key_env: str = ""
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
        """Return the API key, checking environment/config fallbacks."""
        if self._api_key:
            return self._api_key
        if self.api_key_env:
            import os
            return os.environ.get(self.api_key_env)
        return None

    def available_models(self) -> List[ModelInfo]:
        """Return discovered models, falling back to the built-in catalogue."""
        if self._discovered_models is not None:
            return list(self._discovered_models)
        return self._models_from_data(self.default_models)

    def discover_models(self) -> List[ModelInfo]:
        """Discover models from the provider API.

        Providers override this method when their API exposes a model
        catalogue. The default implementation intentionally returns the
        static catalogue so discovery failures never make the router unusable.
        """
        return self._models_from_data(self.default_models)

    def refresh_models(self) -> List[ModelInfo]:
        """Refresh the provider's model catalogue with safe fallback behavior."""
        try:
            discovered = self.discover_models()
            if discovered:
                self._discovered_models = discovered
        except Exception as exc:
            logger.warning("%s model discovery failed: %s", self.provider_name, exc)
        return self.available_models()

    def _models_from_data(self, model_data_list: List[Dict[str, Any]]) -> List[ModelInfo]:
        models: List[ModelInfo] = []
        for model_data in model_data_list:
            model_id = model_data.get("id")
            if not model_id:
                continue
            extra = dict(model_data.get("extra", {}))
            models.append(ModelInfo(
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
                extra={"name": model_data.get("name", model_id), **{
                    k: v for k, v in model_data.items()
                    if k not in {
                        "id", "name", "streaming", "vision", "tool_calling",
                        "embeddings", "audio", "image_generation", "context_length",
                        "max_output_tokens", "input_per_million", "output_per_million", "extra",
                    }
                }},
            ))
        return models

    def capabilities(self) -> Dict[str, Any]:
        return dict(self.default_capabilities)

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            models=self.available_models(),
            capabilities=ModelCapabilities(**{
                "streaming": self.default_capabilities.get("streaming", True),
                "vision": self.default_capabilities.get("vision", False),
                "tool_calling": self.default_capabilities.get("tool_calling", True),
            }),
            context_length=self.context_length_default,
            supports_streaming=self.default_capabilities.get("streaming", True),
            priority=self.priority_default,
            is_local=False,
        )

    def check_health(self) -> bool:
        """Check if the provider is configured with an API key."""
        return self.api_key is not None

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.api_key is not None,
            "model_count": len(self.available_models()),
            "display_name": self.display_name,
        }

    def complete(self, request: RouteRequest) -> str:
        """Stub completion - implement in subclass."""
        raise NotImplementedError(
            f"{self.provider_name}.complete() not implemented - "
            "provider API integration pending."
        )

    def complete_stream(self, request: RouteRequest) -> Any:
        """Stub streaming - implement in subclass."""
        raise NotImplementedError(
            f"{self.provider_name}.complete_stream() not implemented - "
            "provider API integration pending."
        )
