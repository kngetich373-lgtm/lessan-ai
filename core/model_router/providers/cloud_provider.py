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
    
    @property
    def name(self) -> str:
        return self.provider_name
    
    @property
    def api_key(self) -> Optional[str]:
        """Return the API key, checking environment/config fallbacks."""
        if self._api_key:
            return self._api_key
        
        # Check environment variable
        if self.api_key_env:
            import os
            return os.environ.get(self.api_key_env)
        
        return None
    
    def available_models(self) -> List[ModelInfo]:
        models = []
        for model_data in self.default_models:
            models.append(ModelInfo(
                id=model_data["id"],
                capabilities=ModelCapabilities(
                    streaming=model_data.get("streaming", True),
                    vision=model_data.get("vision", False),
                    tool_calling=model_data.get("tool_calling", True),
                    extra=model_data.get("extra", {}),
                ),
                context_length=model_data.get("context_length", self.context_length_default),
                cost=CostMetadata(is_free=model_data.get("extra", {}).get("free", False)),
                extra={"name": model_data.get("name", model_data["id"])},
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
