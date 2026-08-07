"""OpenRouter Provider — adapter for OpenRouter model aggregation."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("OpenRouterProvider")


class OpenRouterProvider(CloudProviderBase):
    """OpenRouter provider adapter (aggregates many models)."""
    
    provider_name = "openrouter"
    display_name = "OpenRouter"
    api_key_env = "OPENROUTER_API_KEY"
    priority_default = 40
    context_length_default = 131072
    
    default_models = [
        {
            "id": "google/gemini-2.0-flash-exp:free",
            "name": "Gemini 2.0 Flash (Free)",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 131072,
            "extra": {"free": True, "reasoning": True},
        },
        {
            "id": "meta-llama/llama-3.3-70b-instruct:free",
            "name": "Llama 3.3 70B (Free)",
            "streaming": True,
            "tool_calling": True,
            "context_length": 131072,
            "extra": {"free": True},
        },
        {
            "id": "qwen/qwen-2.5-72b-instruct:free",
            "name": "Qwen 2.5 72B (Free)",
            "streaming": True,
            "tool_calling": True,
            "context_length": 131072,
            "extra": {"free": True},
        },
    ]
    
    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }
