"""Event topics published by the Gateway Hub subsystem.

All Gateway Hub events are published on the central event bus. Other
subsystems (UI, telemetry, logging) subscribe without coupling to the hub.
"""

# Gateway lifecycle
EV_GATEWAY_CONNECTING = "gateway.connecting"
EV_GATEWAY_CONNECTED = "gateway.connected"
EV_GATEWAY_DISCONNECTED = "gateway.disconnected"
EV_GATEWAY_ERROR = "gateway.error"
EV_GATEWAY_DISABLED = "gateway.disabled"
EV_GATEWAY_ENABLED = "gateway.enabled"
EV_GATEWAY_RECONNECTED = "gateway.reconnected"

# Provider / model events
EV_PROVIDER_DISCOVERED = "gateway.provider_discovered"
EV_PROVIDER_REMOVED = "gateway.provider_removed"
EV_MODEL_DISCOVERED = "gateway.model_discovered"
EV_MODEL_REMOVED = "gateway.model_removed"

# Request / response events
EV_GATEWAY_REQUEST = "gateway.request"
EV_GATEWAY_RESPONSE = "gateway.response"
EV_GATEWAY_STREAM_START = "gateway.stream_start"
EV_GATEWAY_STREAM_CHUNK = "gateway.stream_chunk"
EV_GATEWAY_STREAM_END = "gateway.stream_end"

# Health events
EV_GATEWAY_HEALTH_CHANGED = "gateway.health_changed"
EV_PROVIDER_HEALTH_CHANGED = "gateway.provider_health_changed"

# Metrics events
EV_GATEWAY_METRICS_UPDATED = "gateway.metrics_updated"

# Hub-wide events
EV_HUB_INITIALIZED = "gateway.hub_initialized"
EV_HUB_SHUTDOWN = "gateway.hub_shutdown"
