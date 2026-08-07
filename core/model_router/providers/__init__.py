"""Provider implementations for Lessan AI Model Router.

Each provider implements :class:`BaseModelProvider` and is fully pluggable.
Adding a provider never requires modifying the router.
"""

from core.model_router.providers.cloud_provider import CloudProviderBase
from core.model_router.providers.ollama_provider import OllamaProvider
from core.model_router.providers.gemini_provider import GeminiProvider
from core.model_router.providers.claude_provider import ClaudeProvider
from core.model_router.providers.openai_provider import OpenAIProvider
from core.model_router.providers.openrouter_provider import OpenRouterProvider
from core.model_router.providers.kimi_provider import KimiProvider
from core.model_router.providers.qwen_provider import QwenProvider
from core.model_router.providers.deepseek_provider import DeepSeekProvider

__all__ = [
    "CloudProviderBase",
    "OllamaProvider",
    "GeminiProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "KimiProvider",
    "QwenProvider",
    "DeepSeekProvider",
]
