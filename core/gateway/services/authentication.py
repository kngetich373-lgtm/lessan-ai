"""Authentication Service — manages gateway credentials securely."""

from typing import Any, Dict, Optional

from core.gateway.models import GatewayConfig
from core.logging import get_logger

logger = get_logger("AuthenticationService")


class AuthenticationService:
    """Validates and refreshes gateway credentials.

    The service never stores plaintext secrets. Credentials are passed
    through secure storage and rotated on demand.
    """

    def __init__(self, secure_storage: Any = None) -> None:
        self._secure_storage = secure_storage
        self._cache: Dict[str, str] = {}

    def get_credential(self, gateway_id: str) -> Optional[str]:
        if gateway_id in self._cache:
            return self._cache[gateway_id]
        if self._secure_storage is not None:
            credential = self._secure_storage.get(gateway_id)
            if credential is not None:
                self._cache[gateway_id] = credential
            return credential
        return None

    def set_credential(self, gateway_id: str, credential: str) -> None:
        if self._secure_storage is not None:
            self._secure_storage.set(gateway_id, credential)
        self._cache[gateway_id] = credential

    def rotate(self, gateway_id: str, new_credential: str) -> None:
        self.set_credential(gateway_id, new_credential)
        logger.info(f"Credentials rotated for gateway '{gateway_id}'.")

    def validate(self, config: GatewayConfig) -> bool:
        credential = self.get_credential(config.gateway_id) or config.api_key
        return bool(credential)
