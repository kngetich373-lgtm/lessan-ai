# or_client.py — Backward-compatible compatibility alias.
#
# All LLM routing now flows through the Gateway Hub
# (``core.gateway``).  This module re-exports the new ``GatewayClient``
# as ``client`` so that every existing import pattern in the codebase
# continues to work unchanged:
#
#     from or_client import client
#     text = client.chat(prompt, system="...")
#
# The ``GatewayClient`` preserves the full ``omniroute.client`` interface
# (``chat``, ``chat_json``, ``vision``, ``image_generate``,
# ``available_models``) and transparently falls back to the legacy
# OmniRoute router when no gateway is configured.

from core.gateway.client import GatewayClient
from core.gateway.models import GatewayConfig, GatewayType

from omniroute import (
    OmniRoute,
    TEXT_MODELS,
    VISION_MODELS,
)

client = GatewayClient()

__all__ = [
    "GatewayClient",
    "GatewayConfig",
    "GatewayType",
    "client",
    "OmniRoute",
    "TEXT_MODELS",
    "VISION_MODELS",
]
