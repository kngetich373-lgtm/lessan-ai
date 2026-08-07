"""Gemini Provider — adapter for Google Gemini models."""

from typing import Any, Dict

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("GeminiProvider")


class GeminiProvider(CloudProviderBase):
    """Google Gemini provider adapter."""
    
    provider_name = "gemini"
    display_name = "Google Gemini"
    api_key_env = "GEMINI_API_KEY"
    priority_default = 40
    context_length_default = 128000
    
    default_models = [
        {
            "id": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True, "free": True, "long_context": True},
        },
        {
            "id": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True, "long_context": True},
        },
    ]
    
    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }
    
    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status["free_tier"] = True
        return status
