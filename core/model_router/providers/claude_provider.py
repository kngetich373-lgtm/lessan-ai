"""Claude Provider — adapter for Anthropic Claude models."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("ClaudeProvider")


class ClaudeProvider(CloudProviderBase):
    """Anthropic Claude provider adapter."""
    
    provider_name = "claude"
    display_name = "Anthropic Claude"
    api_key_env = "ANTHROPIC_API_KEY"
    priority_default = 60
    context_length_default = 200000
    
    default_models = [
        {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 200000,
            "extra": {"reasoning": True, "long_context": True},
        },
        {
            "id": "claude-opus-4-20250514",
            "name": "Claude Opus 4",
            "streaming": True,
            "vision": True,
            "tool_calling": True,
            "context_length": 200000,
            "extra": {"reasoning": True, "long_context": True},
        },
    ]
    
    default_capabilities = {
        "streaming": True,
        "vision": True,
        "tool_calling": True,
        "reasoning": True,
    }
