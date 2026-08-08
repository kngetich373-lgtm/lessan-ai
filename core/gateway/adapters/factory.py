"""Adapter Factory — instantiates gateway adapters by gateway type.

Adding a new adapter only requires creating the adapter class in
``core/gateway/adapters/`` and registering it here (or letting
``discover()`` find it automatically via the ``ADAPTER_REGISTRY``
list).
"""

from typing import Callable, Dict, List, Optional, Type

from core.gateway.adapters.base_adapter import BaseGatewayAdapter
from core.gateway.adapters.custom_openai_adapter import CustomOpenAIAdapter
from core.gateway.adapters.deepseek_adapter import DeepSeekAdapter
from core.gateway.adapters.gemini_adapter import GeminiAdapter
from core.gateway.adapters.kimi_adapter import KimiAdapter
from core.gateway.adapters.litellm_adapter import LiteLLMAdapter
from core.gateway.adapters.lmstudio_adapter import LMStudioAdapter
from core.gateway.adapters.omniroute_adapter import OmniRouteAdapter
from core.gateway.adapters.openai_adapter import OpenAIAdapter
from core.gateway.adapters.openrouter_adapter import OpenRouterAdapter
from core.gateway.adapters.ollama_adapter import OllamaAdapter
from core.gateway.adapters.vllm_adapter import VLLMAdapter
from core.gateway.adapters.anthropic_adapter import AnthropicAdapter
from core.logging import get_logger

logger = get_logger("AdapterFactory")

ADAPTER_REGISTRY: Dict[str, Type[BaseGatewayAdapter]] = {
    "omniroute": OmniRouteAdapter,
    "openrouter": OpenRouterAdapter,
    "openai": OpenAIAdapter,
    "deepseek": DeepSeekAdapter,
    "kimi": KimiAdapter,
    "custom_openai": CustomOpenAIAdapter,
    "ollama": OllamaAdapter,
    "litellm": LiteLLMAdapter,
    "lmstudio": LMStudioAdapter,
    "vllm": VLLMAdapter,
    "gemini": GeminiAdapter,
    "anthropic": AnthropicAdapter,
}


def discover() -> List[str]:
    """Return the list of registered gateway types."""
    return list(ADAPTER_REGISTRY.keys())


def create_adapter(gateway_type: str) -> Optional[BaseGatewayAdapter]:
    """Instantiate and return the adapter for ``gateway_type``.

    Returns ``None`` if the type is not registered.
    """
    cls = ADAPTER_REGISTRY.get(gateway_type)
    if cls is None:
        logger.warning(f"No adapter registered for gateway type '{gateway_type}'.")
        return None
    try:
        return cls()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to instantiate adapter '{gateway_type}': {exc}")
        return None


def register_adapter(gateway_type: str, factory: Callable[[], BaseGatewayAdapter]) -> None:
    """Register a custom adapter factory under ``gateway_type``."""
    ADAPTER_REGISTRY[gateway_type] = factory  # type: ignore[assignment]
    logger.info(f"Registered adapter factory for '{gateway_type}'.")


def get_adapter_class(gateway_type: str) -> Optional[Type[BaseGatewayAdapter]]:
    """Return the adapter class for ``gateway_type`` or ``None``."""
    return ADAPTER_REGISTRY.get(gateway_type)


def all_adapters() -> List[BaseGatewayAdapter]:
    """Instantiate every registered adapter."""
    result: List[BaseGatewayAdapter] = []
    for gt in ADAPTER_REGISTRY:
        adapter = create_adapter(gt)
        if adapter is not None:
            result.append(adapter)
    return result
