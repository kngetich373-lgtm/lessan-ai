"""Gateway Hub subsystem for Lessan AI.

The Gateway Hub manages all external AI gateways and provides a single
abstraction layer for the Routing Engine.  The Routing Engine never knows
about individual gateways, providers, or models — it communicates only
with the Gateway Hub.

Public entry points:
    - ``GatewayClient`` — the main client wrapping the hub with
      backward-compatible sync API + modern async API.
    - ``GatewayHub`` — the facade for gateway lifecycle and chat.
    - ``GatewayConfig`` — configuration dataclass for gateways.
"""

from core.gateway.client import GatewayClient
from core.gateway.hub import GatewayHub
from core.gateway.models import (
    GatewayConfig,
    GatewayRequest,
    GatewayResponse,
    GatewayType,
)

__all__ = [
    "GatewayClient",
    "GatewayHub",
    "GatewayConfig",
    "GatewayRequest",
    "GatewayResponse",
    "GatewayType",
]
