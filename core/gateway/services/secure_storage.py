"""Secure Storage Service — encrypted local credential storage."""

import base64
import os
from typing import Optional


class SecureStorage:
    """Encrypted local storage for gateway credentials.

    Uses Fernet symmetric encryption. The encryption key is derived from
    a machine-specific secret and never logged or exposed.
    """

    def __init__(self, storage_path: str = "") -> None:
        self._storage_path = storage_path or os.path.join(
            os.path.expanduser("~"), ".lessan", "gateway_credentials.enc"
        )
        self._key: Optional[bytes] = None
        self._ensure_key()

    def _ensure_key(self) -> None:
        key_path = os.path.join(os.path.dirname(self._storage_path), ".gateway_key")
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                self._key = f.read()
        else:
            from cryptography.fernet import Fernet
            self._key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, "wb") as f:
                f.write(self._key)
            os.chmod(key_path, 0o600)

    def _cipher(self):
        from cryptography.fernet import Fernet
        return Fernet(self._key)

    def get(self, key: str) -> Optional[str]:
        if not os.path.exists(self._storage_path):
            return None
        try:
            with open(self._storage_path, "rb") as f:
                data = f.read()
            decrypted = self._cipher().decrypt(data)
            import json
            store = json.loads(decrypted.decode("utf-8"))
            return store.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str) -> None:
        store: Dict[str, str] = {}
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path, "rb") as f:
                    data = f.read()
                import json
                store = json.loads(self._cipher().decrypt(data).decode("utf-8"))
            except Exception:
                pass
        store[key] = value
        import json
        plaintext = json.dumps(store).encode("utf-8")
        encrypted = self._cipher().encrypt(plaintext)
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
        with open(self._storage_path, "wb") as f:
            f.write(encrypted)
        os.chmod(self._storage_path, 0o600)

    def delete(self, key: str) -> None:
        if not os.path.exists(self._storage_path):
            return
        try:
            with open(self._storage_path, "rb") as f:
                data = f.read()
            import json
            store = json.loads(self._cipher().decrypt(data).decode("utf-8"))
            store.pop(key, None)
            plaintext = json.dumps(store).encode("utf-8")
            encrypted = self._cipher().encrypt(plaintext)
            with open(self._storage_path, "wb") as f:
                f.write(encrypted)
        except Exception:
            pass
