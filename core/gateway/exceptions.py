"""Custom exceptions for the Gateway Hub subsystem."""


class GatewayError(Exception):
    """Base exception for all gateway-related errors."""


class GatewayConnectionError(GatewayError):
    """Raised when a gateway cannot be reached."""


class GatewayAuthenticationError(GatewayError):
    """Raised when authentication with a gateway fails."""


class GatewayDiscoveryError(GatewayError):
    """Raised when provider discovery fails."""


class GatewayTimeoutError(GatewayError):
    """Raised when a gateway operation times out."""


class GatewayRateLimitError(GatewayError):
    """Raised when a gateway returns a rate-limit response."""


class GatewayNotFoundError(GatewayError):
    """Raised when an unknown gateway ID is referenced."""


class GatewayAlreadyConnectedError(GatewayError):
    """Raised when attempting to connect an already-connected gateway."""


class AdapterNotFoundError(GatewayError):
    """Raised when no adapter is registered for a gateway type."""


class ProviderNotFoundError(GatewayError):
    """Raised when a requested provider is not available."""


class ModelNotFoundError(GatewayError):
    """Raised when a requested model is not available."""
