"""Kimi Provider — adapter for Moonshot Kimi models."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("KimiProvider")


class KimiProvider(CloudProviderBase):
    """Moonshot Kimi provider using the OpenAI-compatible API."""

    provider_name = "kimi"
    display_name = "Moonshot Kimi"
    api_key_env = "KIMI_API_KEY"
    api_base = "https://api.moonshot.ai/v1"
    chat_api_style = "openai"
    priority_default = 60
    context_length_default = 128000

    default_models = [
        {"id": "kimi-k2-0711-preview", "name": "Kimi K2 Preview", "streaming": True, "tool_calling": True, "context_length": 128000, "extra": {"reasoning": True, "long_context": True}},
    ]

    default_capabilities = {"streaming": True, "vision": False, "tool_calling": True, "reasoning": True, "long_context": True}
