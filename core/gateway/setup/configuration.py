"""Gateway Setup Configuration — manages gateway configuration persistence."""

import json
import os
from typing import Dict, List, Optional

from core.gateway.models import GatewayConfig, GatewayType
from core.logging import get_logger

logger = get_logger("GatewaySetupConfiguration")


class GatewaySetupConfiguration:
    """Manages gateway configuration loading and saving."""

    def __init__(self, config_path: str = "") -> None:
        self._config_path = config_path or os.path.join(
            os.path.expanduser("~"), ".lessan", "gateway_config.json"
        )

    def load(self) -> List[GatewayConfig]:
        if not os.path.exists(self._config_path):
            return []
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            configs = []
            for item in data.get("gateways", []):
                configs.append(GatewayConfig(
                    gateway_id=item["gateway_id"],
                    gateway_type=GatewayType(item["gateway_type"]),
                    name=item.get("name", ""),
                    display_name=item.get("display_name", ""),
                    enabled=item.get("enabled", True),
                    priority=item.get("priority", 100),
                    api_key=item.get("api_key", ""),
                    base_url=item.get("base_url", ""),
                    timeout=item.get("timeout", 30.0),
                    max_retries=item.get("max_retries", 3),
                    retry_delay=item.get("retry_delay", 1.0),
                    auto_reconnect=item.get("auto_reconnect", True),
                    metadata=item.get("metadata", {}),
                ))
            return configs
        except Exception as exc:
            logger.error(f"Failed to load gateway config: {exc}")
            return []

    def save(self, configs: List[GatewayConfig]) -> None:
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        data = {
            "gateways": [
                {
                    "gateway_id": c.gateway_id,
                    "gateway_type": c.gateway_type.value,
                    "name": c.name,
                    "display_name": c.display_name,
                    "enabled": c.enabled,
                    "priority": c.priority,
                    "api_key": c.api_key,
                    "base_url": c.base_url,
                    "timeout": c.timeout,
                    "max_retries": c.max_retries,
                    "retry_delay": c.retry_delay,
                    "auto_reconnect": c.auto_reconnect,
                    "metadata": c.metadata,
                }
                for c in configs
            ]
        }
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
