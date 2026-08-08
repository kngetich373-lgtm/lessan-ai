"""Gateway Setup Encryption — utility for encrypting/decrypting sensitive config."""

import base64
import os
from typing import Optional


def get_key() -> bytes:
    key_path = os.path.join(os.path.expanduser("~"), ".lessan", ".gateway_key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key)
    os.chmod(key_path, 0o600)
    return key


def encrypt(plaintext: str) -> str:
    from cryptography.fernet import Fernet
    cipher = Fernet(get_key())
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    cipher = Fernet(get_key())
    return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
