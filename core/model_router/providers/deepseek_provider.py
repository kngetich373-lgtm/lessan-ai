"""DeepSeek Provider — adapter for DeepSeek models."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("DeepSeekProvider")


class DeepSeekProvider(CloudProviderBase):
    """DeepSeek provider using the OpenAI-compatible API."""

    provider_name = "deepseek"
    display_name = "DeepSeek"
    api_key_env = "DEEPSEEK_API_KEY"
    api_base = "https://api.deepseek.com/v1"
    chat_api_style = "openai"
    priority_default = 50
    context_length_default = 65536

    default_models = [
        {"id": "deepseek-chat", "name": "DeepSeek Chat", "streaming": True, "tool_calling": True, "context_length": 65536, "extra": {"reasoning": True, "long_context": True, "python": True, "javascript": True}},
        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "streaming": True, "tool_calling": True, "context_length": 65536, "extra": {"reasoning": True, "long_context": True}},
    ]

    default_capabilities = {"streaming": True, "vision": False, "tool_calling": True, "reasoning": True, "long_context": True}
