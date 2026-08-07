"""OpenAI Provider — adapter for OpenAI GPT models."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("OpenAIProvider")


class OpenAIProvider(CloudProviderBase):
    """OpenAI provider adapter."""
    
    provider_name = "openai"
    display_name = "OpenAI"
    api_key_env = "OPENAI_API_KEY"
    priority_default = 60
    context_length_default = 128000
    
    default_models = [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {"reasoning": True},
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 128000,
            "extra": {},
        },
    ]
    
    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }
