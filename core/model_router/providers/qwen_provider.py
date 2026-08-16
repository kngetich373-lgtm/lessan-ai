"""Qwen Provider — adapter for Alibaba Qwen models."""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.logging import get_logger

logger = get_logger("QwenProvider")


class QwenProvider(CloudProviderBase):
    """Alibaba Qwen provider using DashScope's OpenAI-compatible API."""

    provider_name = "qwen"
    display_name = "Alibaba Qwen"
    api_key_env = "QWEN_API_KEY"
    api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_api_style = "openai"
    priority_default = 50
    context_length_default = 131072

    default_models = [
        {"id": "qwen3-coder", "name": "Qwen3 Coder", "streaming": True, "tool_calling": True, "context_length": 131072, "extra": {"reasoning": True, "long_context": True, "python": True, "javascript": True, "cpp": True}},
        {"id": "qwen2.5-72b-instruct", "name": "Qwen2.5 72B Instruct", "streaming": True, "tool_calling": True, "context_length": 131072, "extra": {"reasoning": True, "long_context": True}},
    ]

    default_capabilities = {"streaming": True, "vision": False, "tool_calling": True, "reasoning": True, "long_context": True}
