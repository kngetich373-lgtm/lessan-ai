"""Gateway Setup Wizard — first-launch gateway configuration."""

from typing import Dict, List, Optional

from core.gateway.models import GatewayConfig, GatewayType
from core.logging import get_logger

logger = get_logger("GatewaySetupWizard")


class GatewaySetupWizard:
    """Guides the user through first-launch gateway configuration."""

    SUPPORTED_GATEWAYS = [
        ("omniroute", "OmniRoute", True),
        ("openrouter", "OpenRouter", True),
        ("litellm", "LiteLLM", True),
        ("ollama", "Ollama", True),
        ("lmstudio", "LM Studio", True),
        ("vllm", "vLLM", True),
        ("custom_openai", "Custom OpenAI-Compatible", True),
    ]

    def __init__(self) -> None:
        self._selections: Dict[str, bool] = {}

    def available_gateways(self) -> List[tuple]:
        return list(self.SUPPORTED_GATEWAYS)

    def select(self, gateway_id: str, enabled: bool = True) -> None:
        self._selections[gateway_id] = enabled

    def build_configs(self) -> List[GatewayConfig]:
        configs = []
        for gateway_id, _, _ in self.SUPPORTED_GATEWAYS:
            if self._selections.get(gateway_id, False):
                configs.append(GatewayConfig(
                    gateway_id=gateway_id,
                    gateway_type=GatewayType(gateway_id),
                    name=gateway_id,
                ))
        return configs
