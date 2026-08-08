"""Gateway Setup Validator — validates gateway configurations."""

from typing import List

from core.gateway.models import GatewayConfig
from core.logging import get_logger

logger = get_logger("GatewaySetupValidator")


class GatewaySetupValidator:
    """Validates gateway configurations before connection."""

    def validate(self, config: GatewayConfig) -> List[str]:
        errors = []
        if not config.gateway_id:
            errors.append("Gateway ID is required.")
        if not config.base_url and config.gateway_type != "ollama":
            errors.append("Base URL is required.")
        if config.gateway_type in ("openrouter", "litellm", "custom_openai") and not config.api_key:
            errors.append("API key is required for this gateway type.")
        return errors

    def is_valid(self, config: GatewayConfig) -> bool:
        return len(self.validate(config)) == 0
